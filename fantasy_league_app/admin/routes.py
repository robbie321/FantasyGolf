from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from fantasy_league_app import db, limiter
from fantasy_league_app.models import User, Club, SiteAdmin, Player, PlayerBucket, League, LeagueEntry
import csv
import io
from datetime import datetime, timedelta
from sqlalchemy import func
import requests
import secrets # NEW: For generating secure random strings
from werkzeug.security import generate_password_hash # NEW: For hashing passwords
from fantasy_league_app.league.routes import _create_new_league
from ..utils import is_testing_mode_active, send_winner_notification_email, send_email_verification
import os
from ..auth.decorators import admin_required
from ..forms import EditLeagueForm, LeagueForm, BroadcastNotificationForm, PlayerBucketForm
from ..stripe_client import create_payout
from . import admin_bp
from ..tasks import finalize_finished_leagues, broadcast_notification_task, collect_league_fees
from ..utils import get_league_creation_status

@admin_bp.route('/dashboard')
@admin_required
def admin_dashboard():
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

    # verification
    verified_users = User.query.filter_by(email_verified=True).count()
    unverified_users = User.query.filter_by(email_verified=False).count()

    # Users with expired verification tokens (older than 24 hours)
    expired_cutoff = datetime.utcnow() - timedelta(hours=24)
    expired_unverified = User.query.filter(
        User.email_verified == False,
        User.email_verification_sent_at < expired_cutoff
    ).count()

    stats.update({
        'verified_users': verified_users,
        'unverified_users': unverified_users,
        'expired_unverified': expired_unverified,
        'verification_rate': round((verified_users / total_users * 100), 1) if total_users > 0 else 0
    })

    return render_template('admin/admin_dashboard.html', stats=stats)


# manually verify user
@admin_bp.route('/verify-user/<int:user_id>', methods=['POST'])
@admin_required
def admin_verify_user(user_id):
    user = User.query.get_or_404(user_id)

    if not user.email_verified:
        user.verify_email()
        flash(f'Email verified for user: {user.full_name}', 'success')
    else:
        flash(f'User {user.full_name} is already verified.', 'info')

    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/resend-verification-admin/<int:user_id>', methods=['POST'])
@admin_required
@limiter.limit("5 per hour")
def resend_verification_admin(user_id):
    """Admin resend verification email for a user"""
    user = User.query.get_or_404(user_id)

    if user.email_verified:
        flash(f'User {user.full_name} is already verified.', 'info')
        return redirect(url_for('admin.manage_users'))

    # Generate new token and send email
    user.generate_email_verification_token()
    db.session.commit()

    if send_email_verification(user):
        flash(f'Verification email sent to {user.full_name} ({user.email})', 'success')

        # Log admin action
        current_app.logger.info(f"Admin {current_user.username} resent verification email to user {user.id}")
    else:
        flash(f'Failed to send verification email to {user.full_name}', 'danger')

    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/verification-stats')
@admin_required
def verification_stats():
    """Show detailed email verification statistics"""
    from datetime import datetime, timedelta

    # Calculate stats
    total_users = User.query.count()
    verified_users = User.query.filter_by(email_verified=True).count()
    unverified_users = User.query.filter_by(email_verified=False).count()

    # Users with expired tokens
    expired_cutoff = datetime.utcnow() - timedelta(hours=24)
    expired_unverified = User.query.filter(
        User.email_verified == False,
        User.email_verification_sent_at < expired_cutoff
    ).count()

    # Recent registrations (last 7 days)
    recent_cutoff = datetime.utcnow() - timedelta(days=7)
    recent_registrations = User.query.filter(
        User.created_at >= recent_cutoff  # Assuming you have a created_at field
    ).count()

    # Recent verifications (last 7 days)
    # This would require tracking when verification happened - you could add a verified_at field

    stats = {
        'total_users': total_users,
        'verified_users': verified_users,
        'unverified_users': unverified_users,
        'expired_unverified': expired_unverified,
        'verification_rate': round((verified_users / total_users * 100), 1) if total_users > 0 else 0,
        'recent_registrations': recent_registrations
    }

    # Get list of unverified users
    unverified_list = User.query.filter_by(email_verified=False).order_by(User.email_verification_sent_at.desc()).limit(20).all()

    return render_template('admin/verification_stats.html', stats=stats, unverified_users=unverified_list)

# testing mode

@admin_bp.route('/toggle-testing-mode', methods=['POST'])
@admin_required
def toggle_testing_mode():
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


# ---  Route to manually trigger the finalization task for testing ---
@admin_bp.route('/manual-finalize-leagues', methods=['POST'])
@admin_required
def manual_finalize_leagues():
    """Triggers the background task to finalize all finished leagues."""
    finalize_finished_leagues.delay() # Call the task asynchronously with no arguments
    flash("League finalization process has been started. This may take a few moments.", "info")
    return redirect(url_for('admin.admin_dashboard'))

###### MONITOR REDIS CONNECTIONS ######

###### MONITOR REDIS CONNECTIONS ######

@admin_bp.route('/redis-stats')
@admin_required
def redis_stats():
    """Check Redis connection stats"""
    from fantasy_league_app.extensions import get_redis_client
    import json

    try:
        client = get_redis_client()
        info = client.info('clients')

        stats = {
            'connected_clients': info.get('connected_clients', 0),
            'blocked_clients': info.get('blocked_clients', 0),
            'max_connections': 100,
            'usage_percentage': round((info.get('connected_clients', 0) / 100) * 100, 1)
        }

        return f"<pre>{json.dumps(stats, indent=2)}</pre>"
    except Exception as e:
        import json  # Also add here in case only exception path is taken
        error_response = {
            'error': str(e),
            'connected_clients': 0,
            'blocked_clients': 0,
            'max_connections': 100,
            'usage_percentage': 0
        }
        return f"<pre>{json.dumps(error_response, indent=2)}</pre>", 500


# --- Routes for API Tournament Import ---


@admin_bp.route('/import-tournaments', methods=['GET'])
@admin_required
def import_tournaments():
    """Fetches and displays a list of current and upcoming tournaments from the API."""
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
@admin_required
def import_tournament_action():

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
@admin_required
def refresh_bucket_odds(bucket_id):
    if not getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('main.index'))

    bucket = PlayerBucket.query.get_or_404(bucket_id)
    client = DataGolfClient()

    # 1. Fetch the odds data from the client
    odds_list, error = client.get_betting_odds(bucket.tour)


    print(f'ODDS: {odds_list}')

    if error:
        flash(f'An error occurred while fetching odds from the API: {error}', 'danger')
        return redirect(url_for('admin.add_players_to_bucket', bucket_id=bucket_id))

    if not odds_list:
        flash('Could not retrieve any odds from the API.', 'warning')
        return redirect(url_for('admin.add_players_to_bucket', bucket_id=bucket_id))

    # --- START: New Odds Capping Logic ---

    # 2. Process the data and apply the odds cap
    capped_odds_map = {}
    for player_data in odds_list:
        dg_id = player_data.get('dg_id')
        # Ensure you are getting the correct odds key, e.g., 'odds_bet365'
        odds_from_api = player_data.get('bet365')

        if dg_id and odds_from_api and isinstance(odds_from_api, (int, float)):
            # If the odds are over 80, cap them at 80.
            if odds_from_api > 250:
                capped_odds_map[dg_id] = 250.0
            elif odds_from_api < 1:
                capped_odds_map[dg_id] = 250.0
            else:
                capped_odds_map[dg_id] = float(odds_from_api)

    # --- END: New Odds Capping Logic ---

    # 3. Update players in the database using the capped odds
    updated_count = 0
    for player in bucket.players:
        if player.dg_id and player.dg_id in capped_odds_map:
            player.odds = capped_odds_map[player.dg_id]
            updated_count += 1

    db.session.commit()
    flash(f'Successfully updated and capped odds for {updated_count} players in "{bucket.name}".', 'success')
    return redirect(url_for('admin.add_players_to_bucket', bucket_id=bucket_id))

@admin_bp.route('/add_individual_player', methods=['GET', 'POST'])
@admin_required
def add_individual_player():
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
@admin_required
def upload_players_csv():
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
@admin_required
def manage_player_buckets():
    buckets = PlayerBucket.query.all()
    return render_template('admin/manage_player_buckets.html', buckets=buckets)

@admin_bp.route('/create_player_bucket', methods=['GET', 'POST'])
@admin_required
def create_player_bucket():
    form = PlayerBucketForm()
    if form.validate_on_submit():
        new_bucket = PlayerBucket(
            name=form.name.data,
            description=form.description.data,
            tour=form.tour.data
        )
        db.session.add(new_bucket)
        db.session.commit()
        flash(f'Bucket "{name}" created successfully.', 'success')
        return redirect(url_for('admin.manage_player_buckets'))
    return render_template('admin/create_player_bucket.html', form=form)


# ---  Route for Deleting a Player Bucket ---
@admin_bp.route('/delete_player_bucket/<int:bucket_id>', methods=['POST'])
@admin_required
def delete_player_bucket(bucket_id):

    bucket_to_delete = PlayerBucket.query.get_or_404(bucket_id)

    # Check if any of the leagues using this bucket are still active (i.e., not finalized).
    active_leagues_using_bucket = [
        league for league in bucket_to_delete.leagues if not league.is_finalized
    ]

    if active_leagues_using_bucket:
        count = len(active_leagues_using_bucket)
        flash(f'Cannot delete "{bucket_to_delete.name}" because it is in use by {count} active or upcoming league(s).', 'danger')
        return redirect(url_for('admin.manage_player_buckets'))

    try:
        # If the check passes, it's safe to delete.
        db.session.delete(bucket_to_delete)
        db.session.commit()
        flash(f'Player bucket "{bucket_to_delete.name}" has been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while deleting the bucket: {e}', 'danger')

    return redirect(url_for('admin.manage_player_buckets'))

@admin_bp.route('/player_buckets/<int:bucket_id>', methods=['GET', 'POST'])
@admin_required
def add_players_to_bucket(bucket_id):
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
@admin_required
def remove_player_from_bucket(bucket_id, player_id):

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
@admin_required
def manage_leagues():
    all_leagues = League.query.options(db.joinedload(League.club_host)).order_by(League.id.desc()).all()
    return render_template('admin/manage_leagues.html', leagues=all_leagues)


@admin_bp.route('/leagues/edit/<int:league_id>', methods=['GET', 'POST'])
@admin_required
def edit_league(league_id):
    league = League.query.get_or_404(league_id)
    form = EditLeagueForm(obj=league)

    if form.validate_on_submit():
        league.name = form.name.data
        league.entry_fee = form.entry_fee.data
        league.max_entries = form.max_entries.data
        league.prize_pool_percentage = form.prize_pool_percentage.data

        league.tour = form.tour.data

        db.session.commit()
        flash(f"League '{league.name}' has been updated successfully.", 'success')
        return redirect(url_for('admin.manage_leagues'))

    return render_template('admin/edit_league.html', form=form, league=league, title="Edit League")


@admin_bp.route('/leagues/remove_entry/<int:entry_id>', methods=['POST'])
@admin_required
def remove_league_entry(entry_id):

    entry = LeagueEntry.query.get_or_404(entry_id)
    league_id = entry.league_id

    db.session.delete(entry)
    db.session.commit()

    flash('The league entry has been removed.', 'success')
    return redirect(url_for('admin.edit_league', league_id=league_id))

@admin_bp.route('/leagues/<int:league_id>')
@admin_required
def manage_league_details(league_id):
    league = League.query.get_or_404(league_id)
    return f"<h1>Managing {league.name}</h1><p>Detailed league management tools coming soon!</p>"


# ---  Site Admin's Create Public League Route ---
@admin_bp.route('/create-public-league', methods=['GET', 'POST'])
@admin_required
def create_public_league():

    status = get_league_creation_status()
    if not status["is_creation_enabled"]:
        flash(status["message"], "warning")
        return redirect(url_for('admin.admin_dashboard'))

    form = LeagueForm()
    # Filter player buckets based on available tours
    form.player_bucket_id.choices = [
        (b.id, b.name) for b in PlayerBucket.query.filter(PlayerBucket.tour.in_(status["available_tours"])).order_by('name').all()
    ]

    if form.validate_on_submit():
        new_league, error = _create_new_league(
            name=form.name.data,
            player_bucket_id=form.player_bucket_id.data,
            entry_fee_str=str(form.entry_fee.data),
            prize_amount_str = int(form.prize_amount.data),
            max_entries=form.max_entries.data,
            odds_limit=form.odds_limit.data,
            rules=form.rules.data,
            prize_details=form.prize_details.data,
            # tie_breaker=form.tie_breaker_question.data,
            no_favorites_rule=form.no_favorites_rule.data,
            tour=form.tour.data,
            is_public=True,
            creator_id=current_user.id,
            allow_past_creation=True
        )

        if error:
            flash(error, 'danger')
        else:
            flash(f'Public league "{new_league.name}" created successfully!', 'success')
            return redirect(url_for('admin.manage_leagues'))

    return render_template('admin/create_public_league.html', form=form)


# --- User and Club Management Routes ---

@admin_bp.route('/manage-users')
@admin_required
def manage_users():
    # Fetch all users and clubs
    all_users = User.query.order_by(User.full_name).all()
    all_clubs = Club.query.order_by(Club.club_name).all()

    return render_template('admin/manage_users.html', users=all_users, clubs=all_clubs)

@admin_bp.route('/toggle-user-status/<int:user_id>', methods=['POST'])
@admin_required
def toggle_user_status(user_id):

    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()

    status = "activated" if user.is_active else "deactivated"
    flash(f'User {user.full_name} has been {status}.', 'success')
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/toggle-club-status/<int:club_id>', methods=['POST'])
@admin_required
def toggle_club_status(club_id):

    club = Club.query.get_or_404(club_id)
    club.is_active = not club.is_active
    db.session.commit()

    status = "activated" if club.is_active else "deactivated"
    flash(f'Club {club.club_name} has been {status}.', 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/reset-user-password/<int:user_id>', methods=['POST'])
@admin_required
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)

    # Generate a secure, 10-character temporary password
    temp_password = secrets.token_urlsafe(10)

    user.password_hash = generate_password_hash(temp_password)
    user.password_reset_required = True
    db.session.commit()

    flash(f"Password for {user.full_name} has been reset. The temporary password is: {temp_password}", 'success')
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/reset-club-password/<int:club_id>', methods=['POST'])
@admin_required
def reset_club_password(club_id):
    club = Club.query.get_or_404(club_id)

    temp_password = secrets.token_urlsafe(10)

    club.password_hash = generate_password_hash(temp_password)
    club.password_reset_required = True
    db.session.commit()

    flash(f"Password for {club.club_name} has been reset. The temporary password is: {temp_password}", 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/reset-player-scores')
@admin_required
def reset_player_score():
    """
    This route handles the logic for resetting scores.
    It's triggered by the button press on the admin dashboard.
    It updates the current_score of all players to 0.
    """
    try:
        # This is a bulk update, which is very efficient
        updated_rows = Player.query.update({"current_score": 0})
        db.session.commit()
        print(f"Successfully reset scores for {updated_rows} players.")

        # Send a success message to the user.
        flash('All player scores have been successfully reset to 0.', 'success')
    except Exception as e:
        # If anything goes wrong, roll back the session and show an error.
        db.session.rollback()
        flash(f'An error occurred: {e}', 'danger')

    # Redirect the admin back to the dashboard.
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/leagues/finalize/<int:league_id>', methods=['POST'])
@admin_required
def finalize_league_admin(league_id):

    league = League.query.get_or_404(league_id)

    if not league.has_ended:
        flash('This league cannot be finalized until the tournament is over.', 'warning')
        return redirect(url_for('admin.edit_league', league_id=league.id))

    if league.is_finalized:
        flash('This league has already been finalized.', 'info')
        return redirect(url_for('admin.edit_league', league_id=league.id))

    actual_answer_str = request.form.get('tie_breaker_actual_answer')
    if not actual_answer_str or not actual_answer_str.isdigit():
        flash('You must provide a valid number for the tie-breaker answer.', 'danger')
        return redirect(url_for('admin.edit_league', league_id=league.id))

    actual_answer = int(actual_answer_str)
    entries = league.entries
    if not entries:
        flash('Cannot finalize a league with no entries.', 'warning')
        return redirect(url_for('admin.edit_league', league_id=league.id))

    # Calculate final scores
    for entry in entries:
        entry.total_score = entry.player1.current_score + entry.player2.current_score + entry.player3.current_score

    min_score = min(entry.total_score for entry in entries)
    top_entries = [entry for entry in entries if entry.total_score == min_score]

    winner = None
    if len(top_entries) == 1:
        winner = top_entries[0].user
    else:
        # Sort by the smallest difference to the tie-breaker answer
        winner_entry = min(top_entries, key=lambda x: abs(x.tie_breaker_answer - actual_answer))
        winner = winner_entry.user

    league.is_finalized = True
    league.tie_breaker_actual_answer = actual_answer
    league.winner_id = winner.id

    if not winner.stripe_account_id or not club_admin.stripe_account_id:
        flash("Payout failed: The winner or club admin does not have a connected Stripe account.", "danger")
        return redirect(url_for('league.manage_league', league_id=league.id))

        winner_amount, admin_amount, error = process_league_payouts(league, winner, club_admin)

    if error:
        flash(f"An error occurred with the payout: {error}", "danger")
        return redirect(url_for('admin.edit_league', league_id=league.id))

    # Here you would integrate with Stripe to make the payout
    # For now, we'll just print it for demonstration
    print(f"PAYOUT: Transferring €{final_prize_amount:.2f} to winner {winner.full_name}")



     # --- Archive player scores ---
    all_players_in_league = set()
    for entry in entries:
        all_players_in_league.add(entry.player1)
        all_players_in_league.add(entry.player2)
        all_players_in_league.add(entry.player3)

    for player in all_players_in_league:
        historical_score = PlayerScore(
            player_id=player.id,
            league_id=league.id,
            score=player.current_score
        )
        db.session.add(historical_score)

    db.session.commit()

    # Send notification email using the refactored function
    send_winner_notification_email(league)

    flash(f'League finalized! Winner: {winner.full_name} (€{winner_amount:.2f}). Club Profit: €{admin_amount:.2f}. Payouts processed.', 'success')
    return redirect(url_for('league.manage_league', league_id=league.id))



@admin_bp.route('/send-notification', methods=['GET', 'POST'])
@admin_required
def send_broadcast_notification():
    from ..forms import BroadcastNotificationForm
    from ..tasks import broadcast_notification_task
    from ..push.services import push_service

    form = BroadcastNotificationForm()

    if form.validate_on_submit():
        title = form.title.data
        body = form.body.data

        try:
            # Get notification options from form
            notification_type = getattr(form, 'notification_type', None)
            notification_type = notification_type.data if notification_type else 'broadcast'

            priority = getattr(form, 'priority', None)
            priority = priority.data if priority else 'normal'

            # Enhanced notification data
            notification_data = {
                'title': title,
                'body': body,
                'notification_type': notification_type,
                'icon': '/static/images/icon-192x192.png',
                'badge': '/static/images/badge-72x72.png',
                'tag': f'broadcast_{int(datetime.utcnow().timestamp())}',
                'requireInteraction': priority == 'high',
                'url': '/dashboard',
                'data': {
                    'broadcast_id': str(datetime.utcnow().timestamp()),
                    'admin_user': current_user.username,
                    'sent_at': datetime.utcnow().isoformat(),
                    'priority': priority
                }
            }

            # Add vibration for high priority
            if priority == 'high':
                notification_data['vibrate'] = [200, 100, 200, 100, 200]

            # Send notification using the push service
            if hasattr(push_service, 'send_broadcast_notification'):
                # If you have a dedicated broadcast method
                result = push_service.send_broadcast_notification(**notification_data)
            else:
                # Use the general notification method for all users
                from ..models import User

                # Get all active users
                active_users = User.query.filter_by(is_active=True).all()
                user_ids = [user.id for user in active_users]

                if user_ids:
                    result = push_service.send_notification_sync(
                        user_ids=user_ids,
                        notification_type=notification_type,
                        title=title,
                        body=body,
                        icon=notification_data['icon'],
                        badge=notification_data['badge'],
                        require_interaction=notification_data['requireInteraction'],
                        tag=notification_data['tag'],
                        url=notification_data['url'],
                        vibrate=notification_data.get('vibrate'),
                        data=notification_data['data']
                    )
                else:
                    result = {'success': 0, 'failed': 0, 'total': 0, 'message': 'No active users found'}

            # Log the broadcast
            current_app.logger.info(f"Admin {current_user.username} sent broadcast notification: '{title}' to {result.get('total', 0)} users")

            # Show results to admin
            if result.get('success', 0) > 0:
                flash(f'✅ Broadcast sent successfully to {result["success"]} users!', 'success')

            if result.get('failed', 0) > 0:
                flash(f'⚠️ Failed to send to {result["failed"]} users', 'warning')

            if result.get('total', 0) == 0:
                flash('ℹ️ No users found to send notifications to', 'info')

            # Redirect to prevent resubmission
            return redirect(url_for('admin.send_broadcast_notification'))

        except Exception as e:
            current_app.logger.error(f"Broadcast notification failed: {str(e)}")
            flash(f'❌ Failed to send broadcast notification: {str(e)}', 'danger')

    # Get notification statistics for display
    try:
        from ..models import User, PushSubscription

        total_users = User.query.filter_by(is_active=True).count()
        subscribed_users = db.session.query(PushSubscription.user_id).distinct().count()

        stats = {
            'total_active_users': total_users,
            'subscribed_users': subscribed_users,
            'subscription_rate': round((subscribed_users / total_users * 100), 1) if total_users > 0 else 0
        }
    except Exception:
        stats = {'total_active_users': 0, 'subscribed_users': 0, 'subscription_rate': 0}

    return render_template('admin/send_notification.html', form=form, stats=stats, title="Send Broadcast Notification")


# TESTING

@admin_bp.route('/debug-trigger-scheduler', methods=['POST'])
@admin_required
def debug_trigger_scheduler():
    """Manual debug trigger for the scheduler"""
    from ..tasks import debug_trigger_supervisor, schedule_score_updates_for_the_week

    # Trigger the supervisor task
    result = debug_trigger_supervisor.delay()
    flash(f'Debug supervisor task triggered: {result.id}', 'info')

    # Also directly trigger the main scheduler
    result2 = schedule_score_updates_for_the_week.delay()
    flash(f'Main scheduler task triggered: {result2.id}', 'info')

    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/debug-list-tasks', methods=['POST'])
@admin_required
def debug_list_tasks():
    """Debug route to list scheduled tasks"""
    from ..tasks import debug_list_scheduled_tasks

    result = debug_list_scheduled_tasks.delay()
    flash(f'Task list debug triggered: {result.id}', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/test-celery', methods=['POST'])
@admin_required
def test_celery():
    """Test basic Celery connectivity"""
    from ..tasks import test_celery_connection

    result = test_celery_connection.delay()
    flash(f'Celery test triggered: {result.id}', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/check-task-status/<task_id>')
@admin_required
def check_task_status(task_id):
    """Check the status of a specific task"""
    from .. import celery

    result = celery.AsyncResult(task_id)

    status_info = {
        'task_id': task_id,
        'status': result.status,
        'result': str(result.result) if result.result else None,
        'traceback': result.traceback if result.traceback else None,
        'successful': result.successful(),
        'failed': result.failed(),
        'ready': result.ready(),
    }

    return f"<pre>{json.dumps(status_info, indent=2)}</pre>"

@admin_bp.route('/check-task-result/<task_id>')
@admin_required
def check_task_result(task_id):
    """Get detailed task result information"""
    from .. import celery
    import json

    result = celery.AsyncResult(task_id)

    # Get detailed status
    status_info = {
        'task_id': task_id,
        'status': result.status,
        'successful': result.successful() if result.ready() else None,
        'failed': result.failed() if result.ready() else None,
        'ready': result.ready(),
        'result': str(result.result) if result.result else None,
        'traceback': result.traceback if result.traceback else None,
        'date_done': str(result.date_done) if result.date_done else None,
        'task_name': result.name if hasattr(result, 'name') else None,
    }

    # If failed, get more info
    if result.failed():
        status_info['failure_info'] = {
            'exception': str(result.result),
            'traceback': result.traceback
        }

    return f"<pre>{json.dumps(status_info, indent=2, default=str)}</pre>"

@admin_bp.route('/trigger-score-update-now', methods=['POST'])
@admin_required
def trigger_score_update_now():
    """Manually trigger a score update for testing"""
    from ..tasks import update_player_scores
    from datetime import datetime, timezone, timedelta

    # Set end time to 1 hour from now for testing
    end_time = datetime.now(timezone.utc) + timedelta(hours=1)

    # Trigger for PGA tour
    result = update_player_scores.delay('pga', end_time.isoformat())

    flash(f'Score update task triggered for PGA tour: {result.id}', 'info')
    flash(f'End time set to: {end_time}', 'info')
    flash(f'Check task result at: /admin/check-task-result/{result.id}', 'info')

    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/get-recent-task-results')
@admin_required
def get_recent_task_results():
    """Get results of recent tasks"""
    from .. import celery
    import json

    # Get inspect object
    inspect = celery.control.inspect()
    active = inspect.active()
    reserved = inspect.reserved()

    # Get stats to see recent task execution
    stats = inspect.stats()

    results = {
        'active_tasks': active,
        'reserved_tasks': reserved,
        'worker_stats': stats
    }

    return f"<pre>{json.dumps(results, indent=2, default=str)}</pre>"

@admin_bp.route('/celery-inspect')
@admin_required
def celery_inspect():
    """Inspect Celery worker status"""
    from .. import celery
    import json

    inspect = celery.control.inspect()

    info = {
        'active_tasks': inspect.active(),
        'scheduled_tasks': inspect.scheduled(),
        'reserved_tasks': inspect.reserved(),
        'stats': inspect.stats(),
        'registered_tasks': inspect.registered(),
    }

    return f"<pre>{json.dumps(info, indent=2, default=str)}</pre>"

@admin_bp.route('/test-simple-task', methods=['POST'])
@admin_required
def test_simple_task():
    """Test a very simple task without app context"""
    from ..tasks import simple_test_task

    result = simple_test_task.delay("Hello from admin!")
    flash(f'Simple test task triggered: {result.id}', 'success')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/check-beat-status')
@admin_required
def check_beat_status():
    """Check if Celery Beat scheduler is running and configured properly"""
    from .. import celery
    import json
    from datetime import datetime, timezone

    # Check beat schedule configuration
    beat_schedule = celery.conf.get('beat_schedule', {})

    # Get current time info using built-in timezone
    utc_now = datetime.now(timezone.utc)

    # Check for active scheduled tasks
    inspect = celery.control.inspect()
    scheduled = inspect.scheduled()
    active = inspect.active()
    reserved = inspect.reserved()

    # Check if beat schedule is loaded from config
    config_beat_schedule = current_app.config.get('BEAT_SCHEDULE', {})

    status_info = {
        'celery_beat_schedule_configured': len(beat_schedule) > 0,
        'flask_config_beat_schedule': len(config_beat_schedule) > 0,
        'beat_schedule_source': 'celeryconfig.py' if beat_schedule else 'config.py' if config_beat_schedule else 'NONE',
        'total_scheduled_tasks': len(beat_schedule) if beat_schedule else len(config_beat_schedule),
        'task_names': list(beat_schedule.keys()) if beat_schedule else list(config_beat_schedule.keys()),
        'current_utc_time': utc_now.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'current_weekday': utc_now.weekday(),  # Monday=0, Sunday=6
        'current_weekday_name': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][utc_now.weekday()],
        'scheduled_tasks_in_worker_queue': scheduled,
        'active_tasks_now': active,
        'reserved_tasks': reserved,
        'worker_has_scheduled_tasks': any(scheduled.values()) if scheduled else False,
        'beat_process_indicators': {
            'has_scheduled_queue': scheduled is not None,
            'queue_empty': not any(scheduled.values()) if scheduled else True,
            'likely_beat_status': 'RUNNING' if (scheduled and any(scheduled.values())) else 'NOT RUNNING OR NO PENDING TASKS'
        }
    }

    # Add detailed schedule info
    if beat_schedule:
        status_info['beat_schedule_details'] = {
            task_name: {
                'task': task_config.get('task'),
                'schedule_type': type(task_config.get('schedule')).__name__,
                'schedule_str': str(task_config.get('schedule'))
            } for task_name, task_config in beat_schedule.items()
        }

    return f"<pre>{json.dumps(status_info, indent=2, default=str)}</pre>"

@admin_bp.route('/force-bucket-update', methods=['POST'])
@admin_required
def force_bucket_update():
    """Manually force the bucket update task for testing"""
    from ..tasks import update_player_buckets

    result = update_player_buckets.delay()
    flash(f'Bucket update task forced: {result.id}', 'info')
    flash(f'Check result at: /admin/check-task-result/{result.id}', 'info')

    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/heroku-processes')
@admin_required
def check_heroku_processes():
    """Show information about running Heroku processes"""
    import os

    # This will only work if you add the Heroku CLI info
    process_info = {
        'dyno_name': os.environ.get('DYNO', 'Not on Heroku'),
        'port': os.environ.get('PORT', 'Not set'),
        'redis_url': os.environ.get('REDISCLOUD_URL', 'Not set')[:50] + '...',
        'environment_vars': {
            key: value[:50] + '...' if len(value) > 50 else value
            for key, value in os.environ.items()
            if key.startswith(('CELERY', 'REDIS', 'HEROKU'))
        }
    }

    return f"<pre>{json.dumps(process_info, indent=2)}</pre>"


@admin_bp.route('/simple-celery-check')
@admin_required
def simple_celery_check():
    """Simple check of Celery worker and beat status"""
    from .. import celery
    import json

    try:
        # Basic inspection
        inspect = celery.control.inspect()

        # Get basic info
        stats = inspect.stats()
        active = inspect.active()
        scheduled = inspect.scheduled()

        # Check if we can reach workers
        workers_reachable = stats is not None and len(stats) > 0

        simple_status = {
            'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
            'workers_reachable': workers_reachable,
            'number_of_workers': len(stats) if stats else 0,
            'worker_names': list(stats.keys()) if stats else [],
            'has_scheduled_tasks': bool(scheduled and any(scheduled.values())),
            'has_active_tasks': bool(active and any(active.values())),
            'scheduled_task_count': sum(len(tasks) for tasks in scheduled.values()) if scheduled else 0,
            'active_task_count': sum(len(tasks) for tasks in active.values()) if active else 0,
            'diagnosis': 'UNKNOWN'
        }

        # Simple diagnosis
        if not workers_reachable:
            simple_status['diagnosis'] = 'NO WORKERS RUNNING'
        elif simple_status['has_scheduled_tasks']:
            simple_status['diagnosis'] = 'BEAT SCHEDULER APPEARS TO BE WORKING'
        elif simple_status['scheduled_task_count'] == 0:
            simple_status['diagnosis'] = 'WORKERS RUNNING BUT NO SCHEDULED TASKS (BEAT MAY NOT BE RUNNING)'
        else:
            simple_status['diagnosis'] = 'WORKERS RUNNING, CHECKING BEAT STATUS'

        return f"<pre>{json.dumps(simple_status, indent=2)}</pre>"

    except Exception as e:
        error_info = {
            'error': str(e),
            'error_type': type(e).__name__,
            'diagnosis': 'CELERY CONNECTION ERROR'
        }
        return f"<pre>{json.dumps(error_info, indent=2)}</pre>"


#////////////////
# NOTIFICATIONS


@admin_bp.route('/test-notification', methods=['POST'])
@admin_required
@limiter.limit("3 per hour")
def test_admin_notification():
    """Send a test notification to the current admin user"""
    try:
        # Check if admin has push subscriptions
        from ..models import PushSubscription, User
        from ..push.services import push_service

        # Try to find admin user in regular users table or create test notification
        admin_subscriptions = PushSubscription.query.filter_by(user_id=current_user.id).all()

        if not admin_subscriptions:
            # If admin doesn't have subscriptions, try to find any user with subscriptions for testing
            test_user = db.session.query(User).join(PushSubscription).first()
            if test_user:
                target_user_id = test_user.id
                flash(f'No subscriptions found for admin. Sending test to user: {test_user.full_name}', 'info')
            else:
                flash('No users with push subscriptions found for testing.', 'warning')
                return redirect(url_for('admin.send_broadcast_notification'))
        else:
            target_user_id = current_user.id

        # Send test notification
        result = push_service.send_notification_sync(
            user_ids=[target_user_id],
            notification_type='admin_test',
            title='🧪 Admin Test Notification',
            body=f'This is a test notification sent by {current_user.username} at {datetime.utcnow().strftime("%H:%M:%S")}',
            icon='/static/images/icon-192x192.png',
            require_interaction=True,
            url='/admin/dashboard',
            data={
                'test': True,
                'admin': current_user.username,
                'timestamp': datetime.utcnow().isoformat()
            }
        )

        if result.get('success', 0) > 0:
            flash('✅ Test notification sent successfully!', 'success')
        else:
            flash('❌ Test notification failed to send.', 'danger')

    except Exception as e:
        current_app.logger.error(f"Admin test notification failed: {e}")
        flash(f'Test notification error: {str(e)}', 'danger')

    return redirect(url_for('admin.send_broadcast_notification'))


@admin_bp.route('/notification-analytics')
@admin_required
def notification_analytics():
    """View notification analytics and statistics"""
    try:
        from ..models import User, PushSubscription
        from ..push.models import NotificationLog
        from sqlalchemy import func
        from datetime import datetime, timedelta

        # Basic stats
        total_users = User.query.filter_by(is_active=True).count()
        total_subscriptions = PushSubscription.query.count()
        unique_subscribed_users = db.session.query(PushSubscription.user_id).distinct().count()

        # Recent notification stats (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)

        recent_notifications = NotificationLog.query.filter(
            NotificationLog.sent_at >= thirty_days_ago
        ).count() if hasattr(NotificationLog, 'sent_at') else 0

        successful_notifications = NotificationLog.query.filter(
            NotificationLog.sent_at >= thirty_days_ago,
            NotificationLog.status == 'sent'
        ).count() if hasattr(NotificationLog, 'sent_at') else 0

        # Notification types breakdown
        if hasattr(NotificationLog, 'notification_type'):
            type_stats = db.session.query(
                NotificationLog.notification_type,
                func.count(NotificationLog.id).label('count')
            ).filter(
                NotificationLog.sent_at >= thirty_days_ago
            ).group_by(NotificationLog.notification_type).all()
        else:
            type_stats = []

        analytics_data = {
            'total_users': total_users,
            'total_subscriptions': total_subscriptions,
            'unique_subscribed_users': unique_subscribed_users,
            'subscription_rate': round((unique_subscribed_users / total_users * 100), 1) if total_users > 0 else 0,
            'recent_notifications': recent_notifications,
            'successful_notifications': successful_notifications,
            'success_rate': round((successful_notifications / recent_notifications * 100), 1) if recent_notifications > 0 else 0,
            'type_breakdown': dict(type_stats) if type_stats else {}
        }

        return render_template('admin/notification_analytics.html', data=analytics_data)

    except Exception as e:
        current_app.logger.error(f"Analytics error: {e}")
        flash('Error loading analytics data', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/notification-history')
@admin_required
def notification_history():
    """View recent notification history"""
    try:
        from ..push.models import NotificationLog

        # Get recent notifications (last 50)
        if hasattr(NotificationLog, 'sent_at'):
            recent_notifications = NotificationLog.query.order_by(
                NotificationLog.sent_at.desc()
            ).limit(50).all()
        else:
            recent_notifications = []

        return render_template('admin/notification_history.html', notifications=recent_notifications)

    except Exception as e:
        current_app.logger.error(f"Notification history error: {e}")
        flash('Error loading notification history', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


# Add these notification management routes to your admin dashboard

@admin_bp.route('/clear-inactive-subscriptions', methods=['POST'])
@admin_required
def clear_inactive_subscriptions():
    """Remove inactive push subscriptions"""
    try:
        from ..models import PushSubscription
        from datetime import datetime, timedelta

        # Remove subscriptions older than 90 days with no recent activity
        cutoff_date = datetime.utcnow() - timedelta(days=90)

        if hasattr(PushSubscription, 'last_used'):
            inactive_subs = PushSubscription.query.filter(
                PushSubscription.last_used < cutoff_date
            ).all()
        elif hasattr(PushSubscription, 'created_at'):
            # Fallback to creation date if last_used doesn't exist
            inactive_subs = PushSubscription.query.filter(
                PushSubscription.created_at < cutoff_date
            ).all()
        else:
            inactive_subs = []

        count = len(inactive_subs)
        for sub in inactive_subs:
            db.session.delete(sub)

        db.session.commit()

        flash(f'✅ Cleaned up {count} inactive push subscriptions.', 'success')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Cleanup error: {e}")
        flash('❌ Error cleaning up subscriptions.', 'danger')

    return redirect(url_for('admin.admin_dashboard'))



@admin_bp.route('/debug-vapid-keys')
@admin_required
def debug_vapid_keys():
    """Debug VAPID key configuration"""
    import base64

    try:
        # Get VAPID keys from config
        private_key = current_app.config.get('VAPID_PRIVATE_KEY', '')
        public_key = current_app.config.get('VAPID_PUBLIC_KEY', '')
        claim_email = current_app.config.get('VAPID_CLAIM_EMAIL', '')

        debug_info = {
            'vapid_config': {
                'private_key_exists': bool(private_key),
                'private_key_length': len(private_key),
                'private_key_preview': private_key[:20] + '...' if len(private_key) > 20 else private_key,
                'public_key_exists': bool(public_key),
                'public_key_length': len(public_key),
                'public_key_preview': public_key[:20] + '...' if len(public_key) > 20 else public_key,
                'claim_email': claim_email
            },
            'key_format_analysis': {},
            'conversion_test': {}
        }

        # Analyze key format
        if private_key:
            if len(private_key) < 100 and not private_key.startswith('MI'):
                debug_info['key_format_analysis']['format'] = 'base64url (new format)'
                debug_info['key_format_analysis']['expected_length'] = '43-44 characters'
            elif len(private_key) > 100 or private_key.startswith('MI'):
                debug_info['key_format_analysis']['format'] = 'DER encoded (old format)'
                debug_info['key_format_analysis']['expected_length'] = '100+ characters'
            else:
                debug_info['key_format_analysis']['format'] = 'Unknown format'

        # Test key conversion
        if private_key:
            try:
                if len(private_key) < 100 and not private_key.startswith('MI'):
                    # Test base64url conversion
                    padding = '=' * (4 - len(private_key) % 4) % 4
                    padded_key = private_key + padding
                    regular_b64 = padded_key.replace('-', '+').replace('_', '/')
                    raw_bytes = base64.b64decode(regular_b64)

                    debug_info['conversion_test'] = {
                        'method': 'base64url_to_bytes',
                        'input_length': len(private_key),
                        'padded_length': len(padded_key),
                        'output_length': len(raw_bytes),
                        'success': len(raw_bytes) == 32,
                        'error': None if len(raw_bytes) == 32 else f'Expected 32 bytes, got {len(raw_bytes)}'
                    }

                else:
                    # Test DER conversion
                    der_bytes = base64.b64decode(private_key)
                    if len(der_bytes) >= 68:
                        extracted_key = der_bytes[36:68]
                        debug_info['conversion_test'] = {
                            'method': 'der_extraction',
                            'der_length': len(der_bytes),
                            'extracted_length': len(extracted_key),
                            'success': len(extracted_key) == 32,
                            'error': None if len(extracted_key) == 32 else f'Expected 32 bytes, got {len(extracted_key)}'
                        }
                    else:
                        debug_info['conversion_test'] = {
                            'method': 'der_extraction',
                            'der_length': len(der_bytes),
                            'success': False,
                            'error': f'DER data too short: {len(der_bytes)} bytes'
                        }

            except Exception as e:
                debug_info['conversion_test'] = {
                    'success': False,
                    'error': str(e)
                }

        # Test pywebpush import
        try:
            from pywebpush import webpush
            debug_info['pywebpush_status'] = 'Available'
        except ImportError as e:
            debug_info['pywebpush_status'] = f'Not available: {e}'

        # Generate HTML response
        html = f"""
        <html>
        <head>
            <title>VAPID Keys Debug</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .success {{ color: green; font-weight: bold; }}
                .error {{ color: red; font-weight: bold; }}
                .info {{ color: blue; }}
                pre {{ background: #f5f5f5; padding: 10px; border-radius: 3px; overflow: auto; }}
            </style>
        </head>
        <body>
            <h1>VAPID Keys Debug Information</h1>
            <a href="{url_for('admin.admin_dashboard')}" style="margin-bottom: 20px; display: inline-block;">← Back to Dashboard</a>

            <div class="section">
                <h2>Configuration Status</h2>
                <p><strong>Private Key:</strong> {'✅ Present' if debug_info['vapid_config']['private_key_exists'] else '❌ Missing'}</p>
                <p><strong>Public Key:</strong> {'✅ Present' if debug_info['vapid_config']['public_key_exists'] else '❌ Missing'}</p>
                <p><strong>Claim Email:</strong> {debug_info['vapid_config']['claim_email'] or '❌ Missing'}</p>
                <p><strong>PyWebPush:</strong> {debug_info['pywebpush_status']}</p>
            </div>

            <div class="section">
                <h2>Key Format Analysis</h2>
                <p><strong>Private Key Length:</strong> {debug_info['vapid_config']['private_key_length']} characters</p>
                <p><strong>Detected Format:</strong> {debug_info['key_format_analysis'].get('format', 'Not analyzed')}</p>
                <p><strong>Preview:</strong> <code>{debug_info['vapid_config']['private_key_preview']}</code></p>
            </div>

            <div class="section">
                <h2>Conversion Test</h2>
        """

        if debug_info['conversion_test']:
            if debug_info['conversion_test'].get('success'):
                html += f'<p class="success">✅ Key conversion successful!</p>'
                html += f'<p><strong>Method:</strong> {debug_info["conversion_test"].get("method", "unknown")}</p>'
                html += f'<p><strong>Output Length:</strong> {debug_info["conversion_test"].get("output_length", "unknown")} bytes</p>'
            else:
                html += f'<p class="error">❌ Key conversion failed!</p>'
                html += f'<p><strong>Error:</strong> {debug_info["conversion_test"].get("error", "Unknown error")}</p>'
        else:
            html += '<p class="info">No conversion test performed</p>'

        html += """
            </div>

            <div class="section">
                <h2>Debug Data</h2>
                <pre>{}</pre>
            </div>
        </body>
        </html>
        """.format(json.dumps(debug_info, indent=2))

        return html

    except Exception as e:
        return f"""
        <html>
        <body>
            <h1>VAPID Debug Error</h1>
            <p style="color: red;">Error: {str(e)}</p>
            <a href="{url_for('admin.admin_dashboard')}">← Back to Dashboard</a>
        </body>
        </html>
        """

# Add this route to your admin/routes.py file for debugging

@admin_bp.route('/debug-vapid-conversion')
@admin_required
def debug_vapid_conversion():
    """Debug VAPID key conversion - enhanced version"""
    import base64

    try:
        private_key = current_app.config.get('VAPID_PRIVATE_KEY', '')
        public_key = current_app.config.get('VAPID_PUBLIC_KEY', '')
        claim_email = current_app.config.get('VAPID_CLAIM_EMAIL', '')

        debug_info = {
            'config_status': {
                'private_key_exists': bool(private_key),
                'private_key_length': len(private_key),
                'private_key_preview': private_key[:30] + '...' if len(private_key) > 30 else private_key,
                'public_key_exists': bool(public_key),
                'public_key_length': len(public_key),
                'public_key_preview': public_key[:30] + '...' if len(public_key) > 30 else public_key,
                'claim_email': claim_email
            },
            'format_analysis': {},
            'conversion_attempts': {}
        }

        if private_key:
            # Analyze the key format
            if len(private_key) < 100 and not private_key.startswith('MI'):
                debug_info['format_analysis']['detected_format'] = 'Likely base64url (modern)'
                debug_info['format_analysis']['expected_length'] = '43-44 characters for base64url'
            elif len(private_key) > 100 or private_key.startswith('MI'):
                debug_info['format_analysis']['detected_format'] = 'Likely DER encoded (traditional)'
                debug_info['format_analysis']['expected_length'] = '100+ characters for DER'
            else:
                debug_info['format_analysis']['detected_format'] = 'Unknown format'

            # Test different conversion methods
            conversion_results = []

            # Method 1: Base64url
            try:
                missing_padding = len(private_key) % 4
                padded_key = private_key + ('=' * (4 - missing_padding) if missing_padding else '')
                regular_b64 = padded_key.replace('-', '+').replace('_', '/')
                raw_bytes = base64.b64decode(regular_b64)

                conversion_results.append({
                    'method': 'Base64url conversion',
                    'success': len(raw_bytes) == 32,
                    'result_length': len(raw_bytes),
                    'expected': 32,
                    'preview': list(raw_bytes[:8]) if raw_bytes else None,
                    'error': None if len(raw_bytes) == 32 else f'Got {len(raw_bytes)} bytes, expected 32'
                })
            except Exception as e:
                conversion_results.append({
                    'method': 'Base64url conversion',
                    'success': False,
                    'error': str(e)
                })

            # Method 2: Cryptography library
            try:
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric import ec
                from cryptography.hazmat.backends import default_backend

                der_bytes = base64.b64decode(private_key)
                private_key_obj = serialization.load_der_private_key(
                    der_bytes, password=None, backend=default_backend()
                )

                if isinstance(private_key_obj, ec.EllipticCurvePrivateKey):
                    private_numbers = private_key_obj.private_numbers()
                    raw_bytes = private_numbers.private_value.to_bytes(32, byteorder='big')

                    conversion_results.append({
                        'method': 'Cryptography library (proper DER)',
                        'success': True,
                        'result_length': len(raw_bytes),
                        'expected': 32,
                        'preview': list(raw_bytes[:8]),
                        'error': None
                    })
                else:
                    conversion_results.append({
                        'method': 'Cryptography library (proper DER)',
                        'success': False,
                        'error': f'Not an EC private key: {type(private_key_obj)}'
                    })

            except Exception as e:
                conversion_results.append({
                    'method': 'Cryptography library (proper DER)',
                    'success': False,
                    'error': str(e)
                })

            # Method 3: Manual DER extraction (multiple positions)
            try:
                der_bytes = base64.b64decode(private_key)
                extraction_positions = [(36, 68), (7, 39), (8, 40), (9, 41)]

                for start, end in extraction_positions:
                    if end <= len(der_bytes):
                        extracted = der_bytes[start:end]
                        if len(extracted) == 32:
                            # Check if it's not all zeros or all 255s
                            is_valid = not all(b == 0 for b in extracted) and not all(b == 255 for b in extracted)

                            conversion_results.append({
                                'method': f'Manual DER extraction ({start}-{end})',
                                'success': is_valid,
                                'result_length': len(extracted),
                                'expected': 32,
                                'preview': list(extracted[:8]),
                                'error': None if is_valid else 'Extracted bytes appear invalid (all same value)'
                            })

                            if is_valid:  # If we found a valid extraction, we can stop
                                break

            except Exception as e:
                conversion_results.append({
                    'method': 'Manual DER extraction',
                    'success': False,
                    'error': str(e)
                })

            # Method 4: Raw base64
            try:
                raw_bytes = base64.b64decode(private_key)
                if len(raw_bytes) == 32:
                    conversion_results.append({
                        'method': 'Raw base64 (32-byte key)',
                        'success': True,
                        'result_length': len(raw_bytes),
                        'expected': 32,
                        'preview': list(raw_bytes[:8]),
                        'error': None
                    })
                else:
                    conversion_results.append({
                        'method': 'Raw base64 (32-byte key)',
                        'success': False,
                        'result_length': len(raw_bytes),
                        'expected': 32,
                        'error': f'Got {len(raw_bytes)} bytes, expected 32'
                    })
            except Exception as e:
                conversion_results.append({
                    'method': 'Raw base64 (32-byte key)',
                    'success': False,
                    'error': str(e)
                })

            debug_info['conversion_attempts'] = conversion_results

            # Find the working method
            working_methods = [r for r in conversion_results if r['success']]
            debug_info['working_methods'] = working_methods
            debug_info['recommended_action'] = get_recommended_action(working_methods, debug_info['format_analysis'])

        # Generate HTML response
        html_response = generate_debug_html(debug_info)
        return html_response

    except Exception as e:
        return f"""
        <html>
        <body>
            <h1>Debug Error</h1>
            <p style="color: red;">Error: {str(e)}</p>
            <a href="{url_for('admin.admin_dashboard')}">← Back to Dashboard</a>
        </body>
        </html>
        """, 500


def get_recommended_action(working_methods, format_analysis):
    """Get recommended action based on debug results"""
    if not working_methods:
        return {
            'action': 'GENERATE_NEW_KEYS',
            'description': 'No conversion methods worked. Generate new VAPID keys.',
            'priority': 'HIGH'
        }
    elif len(working_methods) == 1:
        method = working_methods[0]
        return {
            'action': 'UPDATE_CONVERSION_CODE',
            'description': f'Use the {method["method"]} conversion method.',
            'priority': 'MEDIUM',
            'method': method['method']
        }
    else:
        # Multiple methods work - prefer cryptography library if available
        crypto_method = next((m for m in working_methods if 'Cryptography library' in m['method']), None)
        if crypto_method:
            return {
                'action': 'USE_CRYPTOGRAPHY_LIBRARY',
                'description': 'Use the cryptography library method (most reliable).',
                'priority': 'LOW'
            }
        else:
            return {
                'action': 'USE_FIRST_WORKING_METHOD',
                'description': f'Use the {working_methods[0]["method"]} method.',
                'priority': 'MEDIUM',
                'method': working_methods[0]['method']
            }

def generate_debug_html(debug_info):
    """Generate HTML response for debug information"""

    working_methods = debug_info.get('working_methods', [])
    recommendation = debug_info.get('recommended_action', {})

    # Create status indicators
    status_color = '#27ae60' if working_methods else '#e74c3c'
    status_text = f"✅ {len(working_methods)} working method(s) found" if working_methods else "❌ No working conversion methods"

    html = f"""
    <html>
    <head>
        <title>VAPID Key Debug Results</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f7fa; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .card {{ background: white; border-radius: 10px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            .header {{ text-align: center; color: #2c3e50; }}
            .status {{ padding: 15px; border-radius: 8px; margin: 20px 0; font-weight: bold; color: white; background: {status_color}; }}
            .section {{ margin: 30px 0; }}
            .section h3 {{ color: #006a4e; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; }}
            .method {{ background: #f8f9fa; border-left: 4px solid #006a4e; padding: 15px; margin: 10px 0; border-radius: 0 5px 5px 0; }}
            .method.success {{ border-left-color: #27ae60; }}
            .method.failed {{ border-left-color: #e74c3c; }}
            .code {{ background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 5px; font-family: 'Courier New', monospace; white-space: pre-wrap; overflow-x: auto; }}
            .recommendation {{ background: #e8f5e8; border: 2px solid #006a4e; border-radius: 10px; padding: 20px; margin: 20px 0; }}
            .btn {{ background: #006a4e; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px; }}
            .btn:hover {{ background: #004d3a; text-decoration: none; color: white; }}
            .btn-generate {{ background: #e74c3c; }}
            .btn-generate:hover {{ background: #c0392b; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #f8f9fa; font-weight: bold; }}
            .success-text {{ color: #27ae60; font-weight: bold; }}
            .error-text {{ color: #e74c3c; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card header">
                <h1>🔐 VAPID Key Debug Results</h1>
                <div class="status">{status_text}</div>
                <p>Comprehensive analysis of your current VAPID key configuration</p>
            </div>
    """

    # Configuration Status
    config = debug_info['config_status']
    html += f"""
            <div class="card">
                <div class="section">
                    <h3>📋 Configuration Status</h3>
                    <table>
                        <tr><th>Setting</th><th>Status</th><th>Value</th></tr>
                        <tr>
                            <td>Private Key</td>
                            <td class="{'success-text' if config['private_key_exists'] else 'error-text'}">
                                {'✅ Present' if config['private_key_exists'] else '❌ Missing'}
                            </td>
                            <td>{config['private_key_preview']}</td>
                        </tr>
                        <tr>
                            <td>Public Key</td>
                            <td class="{'success-text' if config['public_key_exists'] else 'error-text'}">
                                {'✅ Present' if config['public_key_exists'] else '❌ Missing'}
                            </td>
                            <td>{config['public_key_preview']}</td>
                        </tr>
                        <tr>
                            <td>Claim Email</td>
                            <td class="{'success-text' if config['claim_email'] else 'error-text'}">
                                {'✅ Set' if config['claim_email'] else '❌ Missing'}
                            </td>
                            <td>{config['claim_email'] or 'Not configured'}</td>
                        </tr>
                        <tr>
                            <td>Key Length</td>
                            <td>{config['private_key_length']} characters</td>
                            <td>{debug_info['format_analysis'].get('detected_format', 'Unknown')}</td>
                        </tr>
                    </table>
                </div>
            </div>
    """

    # Conversion Test Results
    html += """
            <div class="card">
                <div class="section">
                    <h3>🧪 Conversion Method Test Results</h3>
    """

    for result in debug_info['conversion_attempts']:
        success_class = 'success' if result['success'] else 'failed'
        status_icon = '✅' if result['success'] else '❌'

        html += f"""
                    <div class="method {success_class}">
                        <h4>{status_icon} {result['method']}</h4>
        """

        if result['success']:
            html += f"""
                        <p><strong>Result:</strong> Success! Extracted {result['result_length']}-byte key</p>
                        <p><strong>Preview:</strong> {result['preview']}</p>
            """
        else:
            html += f"""
                        <p><strong>Error:</strong> {result.get('error', 'Unknown error')}</p>
            """

        html += "</div>"

    html += "</div></div>"

    # Recommendation Section
    html += f"""
            <div class="recommendation">
                <h3>💡 Recommended Action: {recommendation.get('action', 'UNKNOWN')}</h3>
                <p><strong>Priority:</strong> {recommendation.get('priority', 'UNKNOWN')}</p>
                <p>{recommendation.get('description', 'No recommendation available')}</p>
    """

    if recommendation.get('action') == 'GENERATE_NEW_KEYS':
        html += f"""
                <a href="{url_for('admin.generate_vapid_keys')}" class="btn btn-generate">
                    🔄 Generate New VAPID Keys
                </a>
        """
    elif working_methods:
        best_method = working_methods[0]
        html += f"""
                <div style="margin-top: 20px;">
                    <h4>Recommended Conversion Code:</h4>
                    <div class="code">
def _convert_der_private_key(self, der_base64_key):
    \"\"\"Convert VAPID private key using {best_method['method']}\"\"\"
    try:
        current_app.logger.info("Converting VAPID key using {best_method['method']}")
        """

        if 'Base64url' in best_method['method']:
            html += """
        # Base64url conversion
        missing_padding = len(der_base64_key) % 4
        if missing_padding:
            padded_key = der_base64_key + '=' * (4 - missing_padding)
        else:
            padded_key = der_base64_key

        regular_b64 = padded_key.replace('-', '+').replace('_', '/')
        raw_bytes = base64.b64decode(regular_b64)

        if len(raw_bytes) != 32:
            raise ValueError(f"Invalid key length: {len(raw_bytes)}")

        return raw_bytes
            """
        elif 'Cryptography library' in best_method['method']:
            html += """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.backends import default_backend

        der_bytes = base64.b64decode(der_base64_key)
        private_key = serialization.load_der_private_key(
            der_bytes, password=None, backend=default_backend()
        )

        private_numbers = private_key.private_numbers()
        return private_numbers.private_value.to_bytes(32, byteorder='big')
            """
        elif 'Manual DER' in best_method['method']:
            # Extract position from method name
            import re
            position_match = re.search(r'\((\d+)-(\d+)\)', best_method['method'])
            if position_match:
                start, end = position_match.groups()
                html += f"""
        der_bytes = base64.b64decode(der_base64_key)
        raw_bytes = der_bytes[{start}:{end}]

        if len(raw_bytes) != 32:
            raise ValueError(f"Invalid key length: {{len(raw_bytes)}}")

        return raw_bytes
                """

        html += """
    except Exception as e:
        current_app.logger.error(f"VAPID key conversion failed: {e}")
        return None
                    </div>
                </div>
        """

    html += "</div>"

    # Action Buttons
    html += f"""
            <div class="card" style="text-align: center;">
                <a href="{url_for('admin.admin_dashboard')}" class="btn">← Back to Dashboard</a>
                <a href="{url_for('admin.debug_vapid_keys')}" class="btn">🔍 View Detailed VAPID Info</a>
                <a href="{url_for('admin.generate_vapid_keys')}" class="btn btn-generate">🔄 Generate New Keys</a>
            </div>
        </div>
    </body>
    </html>
    """

    return html

@admin_bp.route('/generate-vapid-keys')
@admin_required
def generate_vapid_keys():
    """Admin route to generate new VAPID keys"""
    try:
        private_key, public_key = generate_new_vapid_keys()

        if private_key and public_key:
            return f"""
            <html>
            <head><title>New VAPID Keys</title></head>
            <body style="font-family: Arial, sans-serif; margin: 40px;">
                <h1>🔐 New VAPID Keys Generated</h1>
                <div style="background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3>Add these to your config.py:</h3>
                    <pre style="background: #fff; padding: 15px; border-radius: 5px; overflow-x: auto;">
                        VAPID_PRIVATE_KEY = '{private_key}'
                        VAPID_PUBLIC_KEY = '{public_key}'</pre>
                </div>
                <p><strong>⚠️ Important:</strong> Update your config and restart the application!</p>
                <a href="{url_for('admin.admin_dashboard')}" style="background: #006a4e; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">← Back to Dashboard</a>
            </body>
            </html>
            """
        else:
            return "Error generating keys", 500

    except Exception as e:
        return f"Error: {str(e)}", 500


@admin_bp.route('/analytics/onboarding')
@admin_required
def onboarding_analytics():
    total_users = User.query.count()
    tutorial_completed = User.query.filter_by(tutorial_completed=True).count()

    # Average time to complete tutorial
    avg_completion_time = db.session.query(
        func.avg(User.tutorial_completion_date - User.first_login)
    ).filter(User.tutorial_completed == True).scalar()

    # Most dismissed tips
    all_dismissed = db.session.query(User.tips_dismissed).filter(
        User.tips_dismissed.isnot(None)
    ).all()

    tip_counts = {}
    for (tips,) in all_dismissed:
        for tip in tips:
            tip_counts[tip] = tip_counts.get(tip, 0) + 1

    return render_template('admin/onboarding_analytics.html',
        total_users=total_users,
        tutorial_completed=tutorial_completed,
        completion_rate=(tutorial_completed/total_users*100) if total_users > 0 else 0,
        avg_completion_time=avg_completion_time,
        top_dismissed_tips=sorted(tip_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    )