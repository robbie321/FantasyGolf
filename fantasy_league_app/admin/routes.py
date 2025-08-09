from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from fantasy_league_app import db
from fantasy_league_app.models import User, Club, SiteAdmin, Player, PlayerBucket, League, LeagueEntry
import csv
import io
from datetime import datetime, timedelta
from sqlalchemy import func
import requests
import secrets # NEW: For generating secure random strings
from werkzeug.security import generate_password_hash # NEW: For hashing passwords
from fantasy_league_app.league.routes import _create_new_league
from fantasy_league_app.utils import is_testing_mode_active
import os

from . import admin_bp

@admin_bp.route('/dashboard')
@login_required
def admin_dashboard():
    if not getattr(current_user, 'is_site_admin', False):
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))

    # --- Analytics Calculations ---
    total_users = User.query.count()
    total_clubs = Club.query.count()
    total_entries = LeagueEntry.query.count()
    active_leagues = League.query.filter(League.end_date >= datetime.utcnow()).count()

    # Financial Snapshot
    timeframe = request.args.get('revenue_timeframe', 'all')
    now = datetime.utcnow()
    start_date = None

    if timeframe == 'day':
        start_date = now - timedelta(days=1)
    elif timeframe == 'week':
        start_date = now - timedelta(weeks=1)
    elif timeframe == 'month':
        start_date = now - timedelta(days=30)
    elif timeframe == 'year':
        start_date = now - timedelta(days=365)

    # This query structure is more explicit and resolves the ambiguity.
    query = db.session.query(func.sum(League.entry_fee)).select_from(LeagueEntry).join(League, LeagueEntry.league_id == League.id)
    if start_date:
        query = query.filter(League.start_date >= start_date)
    total_revenue = query.scalar()

    total_revenue = total_revenue or 0

    stats = {
        'total_users': total_users,
        'total_clubs': total_clubs,
        'active_leagues': active_leagues,
        'total_entries': total_entries,
        'total_revenue': total_revenue,
        'selected_timeframe': timeframe
    }

    stats['testing_mode_active'] = is_testing_mode_active()

    return render_template('admin/admin_dashboard.html', stats=stats)


# testing mode

@admin_bp.route('/toggle-testing-mode', methods=['POST'])
@login_required
def toggle_testing_mode():
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    flag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', current_app.config['TESTING_MODE_FLAG'])

    if is_testing_mode_active():
        # If it's active, turn it off by deleting the file
        os.remove(flag_path)
        flash('Testing Mode has been deactivated.', 'success')
    else:
        # If it's inactive, turn it on by creating the file
        with open(flag_path, 'w') as f:
            f.write('active')
        flash('Testing Mode has been activated. Users can now join leagues past the deadline.', 'success')

    return redirect(url_for('admin.admin_dashboard'))

# --- Routes for API Tournament Import ---


@admin_bp.route('/import-tournaments', methods=['GET'])
@login_required
def import_tournaments():
    """Fetches and displays a list of current and upcoming tournaments from the API."""
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    client = DataGolfClient()
    # Call the new client to get the schedule
    all_tournaments, error = client.get_tournament_schedule()

    if error:
        flash(f'Error fetching tournament schedule from API: {error}', 'danger')
        # If there's an error, pass an empty list to the template
        return render_template('admin/import_tournaments.html', tournaments=[])

    # This is the logic that filters for current and upcoming tournaments
    tournaments = []
    today = datetime.utcnow().date()
    for t in all_tournaments:
        start_date = datetime.strptime(t.get('start_date'), '%Y-%m-%d').date()
        # This logic correctly filters for tournaments starting this week or in the future
        if start_date >= today - timedelta(days=today.weekday()):
            tournaments.append(t)

    return render_template('admin/import_tournaments.html', tournaments=tournaments)


@admin_bp.route('/import-tournament', methods=['POST'])
@login_required
def import_tournament_action():
    """Imports players for a selected tournament, creates a bucket, and adds players."""
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    event_id = request.form.get('event_id')
    event_name = request.form.get('event_name')

    if PlayerBucket.query.filter_by(name=event_name).first():
        flash(f'A player bucket named "{event_name}" already exists.', 'warning')
        return redirect(url_for('admin.import_tournaments'))

    client = DataGolfClient()
    player_odds = {}

    # --- REFACTORED ODDS FETCHING ---
    odds_list, odds_error = client.get_betting_odds()
    if odds_error:
        flash(f'Could not fetch betting odds; player odds will default to 0. Error: {odds_error}', 'warning')
    else:
        # The client now directly returns the list of player data dictionaries
        for player_data in odds_list:
            dg_id = player_data.get('dg_id')
            bet365_odds = player_data.get('bet365')
            if dg_id and bet365_odds is not None:
                player_odds[dg_id] = float(bet365_odds)

    # --- REFACTORED PLAYER FIELD FETCHING ---
    player_list, field_error = client.get_tournament_field_updates(event_id)
    if field_error:
        flash(f'Error fetching player field from API: {field_error}', 'danger')
        return redirect(url_for('admin.manage_player_buckets'))

    if not player_list:
        flash('Could not fetch player field for this tournament.', 'warning')
        return redirect(url_for('admin.import_tournaments'))

    new_bucket = PlayerBucket(name=event_name, description=f"Players for {event_name}")
    db.session.add(new_bucket)

    new_players_count = 0
    updated_players_count = 0

    for api_player in player_list:
        dg_id = api_player.get('dg_id')
        if not dg_id:
            continue

        odds = player_odds.get(dg_id, 0.0)
        player = Player.query.filter_by(dg_id=dg_id).first()

        if not player:
            player_name_parts = api_player.get('player_name', '').split(' ')
            name = player_name_parts[0]
            surname = ' '.join(player_name_parts[1:])
            new_player = Player(
                dg_id=dg_id,
                name=name,
                surname=surname,
                odds=odds
            )
            db.session.add(new_player)
            new_bucket.players.append(new_player)
            new_players_count += 1
        else:
            player.odds = odds
            updated_players_count += 1
            if player not in new_bucket.players:
                new_bucket.players.append(player)

    db.session.commit()

    flash(f'Successfully created bucket "{event_name}" with {len(new_bucket.players)} players.', 'success')
    if new_players_count > 0:
        flash(f'{new_players_count} new players were added to the main database.', 'info')
    if updated_players_count > 0:
        flash(f'Updated odds for {updated_players_count} existing players.', 'info')

    return redirect(url_for('admin.manage_player_buckets'))



from ..data_golf_client import DataGolfClient # Make sure this import is at the top

@admin_bp.route('/player_buckets/<int:bucket_id>/refresh_odds', methods=['POST'])
@login_required
def refresh_bucket_odds(bucket_id):
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    bucket = PlayerBucket.query.get_or_404(bucket_id)
    client = DataGolfClient()
    player_odds = {}

    # 1. Use the client to fetch the odds data
    odds_list, error = client.get_betting_odds()

    # 2. Handle potential errors from the client
    if error:
        flash(f'An error occurred while fetching odds from the API: {error}', 'danger')
        return redirect(url_for('admin.add_players_to_bucket', bucket_id=bucket_id))

    # 3. Process the data returned by the client
    for player_data in odds_list:
        dg_id = player_data.get('dg_id')
        bet365_odds = player_data.get('bet365')
        if dg_id and bet365_odds is not None:
            player_odds[dg_id] = float(bet365_odds)

    if not player_odds:
        flash('Could not retrieve any odds from the API.', 'warning')
        return redirect(url_for('admin.add_players_to_bucket', bucket_id=bucket_id))

    # 4. Update players in the database
    updated_count = 0
    for player in bucket.players:
        if player.dg_id and player.dg_id in player_odds:
            player.odds = player_odds[player.dg_id]
            updated_count += 1

    db.session.commit()
    flash(f'Successfully updated odds for {updated_count} players in "{bucket.name}".', 'success')

    return redirect(url_for('admin.add_players_to_bucket', bucket_id=bucket_id))

@admin_bp.route('/add_individual_player', methods=['GET', 'POST'])
@login_required
def add_individual_player():
    if not getattr(current_user, 'is_site_admin', False): return redirect(url_for('main.index'))
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']
        odds = float(request.form['odds'])
        new_player = Player(name=name, surname=surname, odds=odds)
        db.session.add(new_player)
        db.session.commit()
        flash(f'Player {name} {surname} added successfully!', 'success')
        return redirect(url_for('admin.add_individual_player'))
    return render_template('admin/add_individual_player.html')

@admin_bp.route('/upload_players_csv', methods=['GET', 'POST'])
@login_required
def upload_players_csv():
    if not getattr(current_user, 'is_site_admin', False): return redirect(url_for('main.index'))
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['csv_file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        if file:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.reader(stream)
            next(csv_reader, None)
            for row in csv_reader:
                name, surname, odds = row
                player = Player(name=name, surname=surname, odds=float(odds))
                db.session.add(player)
            db.session.commit()
            flash('Players from CSV uploaded successfully!', 'success')
            return redirect(url_for('admin.admin_dashboard'))
    return render_template('admin/upload_players_csv.html')

@admin_bp.route('/player_buckets', methods=['GET', 'POST'])
@login_required
def manage_player_buckets():
    if not getattr(current_user, 'is_site_admin', False): return redirect(url_for('main.index'))
    buckets = PlayerBucket.query.all()
    return render_template('admin/manage_player_buckets.html', buckets=buckets)

@admin_bp.route('/create_player_bucket', methods=['GET', 'POST'])
@login_required
def create_player_bucket():
    if not getattr(current_user, 'is_site_admin', False): return redirect(url_for('main.index'))
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description')
        new_bucket = PlayerBucket(name=name, description=description)
        db.session.add(new_bucket)
        db.session.commit()
        flash(f'Bucket "{name}" created successfully.', 'success')
        return redirect(url_for('admin.manage_player_buckets'))
    return render_template('admin/create_player_bucket.html')


# ---  Route for Deleting a Player Bucket ---
@admin_bp.route('/delete_player_bucket/<int:bucket_id>', methods=['POST'])
@login_required
def delete_player_bucket(bucket_id):
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    bucket_to_delete = PlayerBucket.query.get_or_404(bucket_id)

    # Safety Check: Check if any leagues are using this bucket
    leagues_using_bucket = League.query.filter_by(player_bucket_id=bucket_id).count()
    if leagues_using_bucket > 0:
        flash(f'Cannot delete "{bucket_to_delete.name}" because it is currently in use by {leagues_using_bucket} league(s).', 'danger')
        return redirect(url_for('admin.manage_player_buckets'))

    try:
        db.session.delete(bucket_to_delete)
        db.session.commit()
        flash(f'Player bucket "{bucket_to_delete.name}" has been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while deleting the bucket: {e}', 'danger')

    return redirect(url_for('admin.manage_player_buckets'))

@admin_bp.route('/player_buckets/<int:bucket_id>', methods=['GET', 'POST'])
@login_required
def add_players_to_bucket(bucket_id):
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    bucket = PlayerBucket.query.get_or_404(bucket_id)

    if request.method == 'POST':
        if 'add_individual' in request.form:
            player_id = request.form.get('player_id')
            if player_id:
                player = Player.query.get(player_id)
                if player and player not in bucket.players:
                    bucket.players.append(player)
                    db.session.commit()
                    flash(f'{player.full_name()} added to bucket.', 'success')
                else:
                    flash('Player already in bucket or not found.', 'warning')

        elif 'upload_csv' in request.form:
            file = request.files.get('file')
            if file and file.filename != '':
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_reader = csv.reader(stream)
                next(csv_reader, None)
                count = 0
                for row in csv_reader:
                    name, surname = row[0], row[1]
                    player = Player.query.filter_by(name=name, surname=surname).first()
                    if player and player not in bucket.players:
                        bucket.players.append(player)
                        count += 1
                db.session.commit()
                flash(f'{count} players from CSV added to the bucket.', 'success')

        return redirect(url_for('admin.add_players_to_bucket', bucket_id=bucket.id))

    players_in_bucket = bucket.players
    all_player_ids = {player.id for player in players_in_bucket}
    players_not_in_bucket = Player.query.filter(Player.id.notin_(all_player_ids)).all()

    return render_template(
        'admin/add_players_to_bucket.html',
        bucket=bucket,
        players_in_bucket=players_in_bucket,
        players_not_in_bucket=players_not_in_bucket
    )

@admin_bp.route('/player_buckets/<int:bucket_id>/remove/<int:player_id>', methods=['POST'])
@login_required
def remove_player_from_bucket(bucket_id, player_id):
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    bucket = PlayerBucket.query.get_or_404(bucket_id)
    player = Player.query.get_or_404(player_id)

    if player in bucket.players:
        bucket.players.remove(player)
        db.session.commit()
        flash(f'{player.full_name()} has been removed from the bucket.', 'success')
    else:
        flash('Player was not in the bucket.', 'warning')

    return redirect(url_for('admin.add_players_to_bucket', bucket_id=bucket.id))

@admin_bp.route('/leagues')
@login_required
def manage_leagues():
    if not getattr(current_user, 'is_site_admin', False):
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    all_leagues = League.query.options(db.joinedload(League.club_host)).order_by(League.id.desc()).all()
    return render_template('admin/manage_leagues.html', leagues=all_leagues)


@admin_bp.route('/leagues/edit/<int:league_id>', methods=['GET', 'POST'])
@login_required
def edit_league(league_id):
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    league = League.query.get_or_404(league_id)

    if request.method == 'POST':
        # Update league details from the form
        league.name = request.form.get('name')
        start_date_str = request.form.get('start_date')
        if start_date_str:
            league.start_date = datetime.fromisoformat(start_date_str)
            league.end_date = league.start_date + timedelta(days=4)

        db.session.commit()
        flash(f'League "{league.name}" has been updated.', 'success')
        return redirect(url_for('admin.edit_league', league_id=league.id))

    entries = LeagueEntry.query.filter_by(league_id=league.id).all()
    return render_template('admin/edit_league.html', league=league, entries=entries)


@admin_bp.route('/leagues/remove_entry/<int:entry_id>', methods=['POST'])
@login_required
def remove_league_entry(entry_id):
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    entry = LeagueEntry.query.get_or_404(entry_id)
    league_id = entry.league_id

    db.session.delete(entry)
    db.session.commit()

    flash('The league entry has been removed.', 'success')
    return redirect(url_for('admin.edit_league', league_id=league_id))

@admin_bp.route('/leagues/<int:league_id>')
@login_required
def manage_league_details(league_id):
    if not getattr(current_user, 'is_site_admin', False):
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    league = League.query.get_or_404(league_id)
    return f"<h1>Managing {league.name}</h1><p>Detailed league management tools coming soon!</p>"


# ---  Site Admin's Create Public League Route ---
@admin_bp.route('/create-public-league', methods=['GET', 'POST'])
@login_required
def create_public_league():
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    player_buckets = PlayerBucket.query.all()

    if request.method == 'POST':
        new_league, error = _create_new_league(
            name=request.form.get('name'),
            start_date_str=request.form.get('start_date'),
            player_bucket_id=request.form.get('player_bucket_id'),
            entry_fee_str=request.form.get('entry_fee'),
            rules=request.form.get('rules'),
            prize_details=request.form.get('prize_details'),
            tie_breaker=request.form.get('tie_breaker_question'),
            tour=request.form.get('tour'),
            is_public=True, # Site Admin creates public leagues
            allow_past_creation=True
        )

        if error:
            flash(error, 'danger')
            return render_template('admin/create_public_league.html', player_buckets=player_buckets, form_data=request.form)

        flash(f'Public league "{new_league.name}" created successfully!', 'success')
        return redirect(url_for('admin.manage_leagues'))

    return render_template('admin/create_public_league.html', player_buckets=player_buckets)


# --- User and Club Management Routes ---

@admin_bp.route('/manage-users')
@login_required
def manage_users():
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    # Fetch all users and clubs
    all_users = User.query.order_by(User.full_name).all()
    all_clubs = Club.query.order_by(Club.club_name).all()

    return render_template('admin/manage_users.html', users=all_users, clubs=all_clubs)

@admin_bp.route('/toggle-user-status/<int:user_id>', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()

    status = "activated" if user.is_active else "deactivated"
    flash(f'User {user.full_name} has been {status}.', 'success')
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/toggle-club-status/<int:club_id>', methods=['POST'])
@login_required
def toggle_club_status(club_id):
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    club = Club.query.get_or_404(club_id)
    club.is_active = not club.is_active
    db.session.commit()

    status = "activated" if club.is_active else "deactivated"
    flash(f'Club {club.club_name} has been {status}.', 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/reset-user-password/<int:user_id>', methods=['POST'])
@login_required
def reset_user_password(user_id):
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    user = User.query.get_or_404(user_id)

    # Generate a secure, 10-character temporary password
    temp_password = secrets.token_urlsafe(10)

    user.password_hash = generate_password_hash(temp_password)
    user.password_reset_required = True
    db.session.commit()

    flash(f"Password for {user.full_name} has been reset. The temporary password is: {temp_password}", 'success')
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/reset-club-password/<int:club_id>', methods=['POST'])
@login_required
def reset_club_password(club_id):
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    club = Club.query.get_or_404(club_id)

    temp_password = secrets.token_urlsafe(10)

    club.password_hash = generate_password_hash(temp_password)
    club.password_reset_required = True
    db.session.commit()

    flash(f"Password for {club.club_name} has been reset. The temporary password is: {temp_password}", 'success')
    return redirect(url_for('admin.manage_users'))


