from flask_mail import Message
from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_required, current_user
from fantasy_league_app import db, mail
from fantasy_league_app.models import League, LeagueEntry, Player, PlayerBucket
from fantasy_league_app.utils import is_testing_mode_active
from . import league_bp
import random
import string
from datetime import datetime, timedelta
import stripe
from ..data_golf_client import DataGolfClient



def _get_sorted_leaderboard(league_id):
    """Calculates scores and returns a sorted list of entries for a given league."""
    league = League.query.get_or_404(league_id)
    sorted_entries = []

    if league.has_entry_deadline_passed:
        entries = LeagueEntry.query.filter_by(league_id=league.id).all()
        for entry in entries:
            entry.total_score = entry.player1.current_score + entry.player2.current_score + entry.player3.current_score

        sorted_entries = sorted(entries, key=lambda e: e.total_score)

    return league, sorted_entries

# fantasy_league_app/league/routes.py

# Make sure the client is imported at the top of the file
from ..data_golf_client import DataGolfClient

def _create_new_league(name, start_date_str, player_bucket_id, entry_fee_str, prize_amount_str, rules, prize_details, tie_breaker, tour, max_entries, odds_limit, no_favorites_rule, is_public=False, club_creator=None, user_creator=None, allow_past_creation=False):
    """
    A helper function to handle the creation of any type of league.
    Returns (new_league, error_message)
    """
    # --- Validation ---
    try:
        entry_fee = float(entry_fee_str)
        prize_amount = float(prize_amount_str)
        start_date = datetime.fromisoformat(start_date_str)
        max_entries_val = int(max_entries) if max_entries else None
        odds_limit_val = int(odds_limit) if odds_limit else None
    except (ValueError, TypeError):
        return None, "Invalid date, fee, or prize format."

    if League.query.filter_by(name=name).first():
        return None, f"A league with the name '{name}' already exists. Please choose a different name."

    if not allow_past_creation and start_date < datetime.utcnow() + timedelta(days=3):
        return None, "The tournament start date must be at least 3 days in the future."

    if 0 < entry_fee < 5:
        return None, "The entry fee must be €0.00 or at least €5.00."

    # --- Logic ---
    end_date = start_date + timedelta(days=4)
    league_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    while League.query.filter_by(league_code=league_code).first():
        league_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

    new_league = League(
        name=name, league_code=league_code, entry_fee=entry_fee, prize_amount=prize_amount,
        max_entries=max_entries_val, odds_limit=odds_limit_val,
        no_favorites_rule=int(no_favorites_rule), prize_details=prize_details, rules=rules,
        tie_breaker_question=tie_breaker, player_bucket_id=player_bucket_id,
        start_date=start_date, end_date=end_date, is_public=is_public, tour=tour,
        club_id=club_creator.id if club_creator else None,
        user_id=user_creator.id if user_creator else None
    )
    db.session.add(new_league)
    db.session.commit()

    # --- REFACTORED: Fetch initial scores using the client ---
    if start_date < datetime.utcnow():
        print(f"--- League '{name}' created for an active tournament. Fetching initial scores. ---")
        client = DataGolfClient()
        live_stats, error = client.get_live_tournament_stats(tour)

        if error:
            print(f"ERROR: Could not fetch initial scores for new league. {error}")
        else:
            bucket_players = Player.query.join(PlayerBucket.players).filter(PlayerBucket.id == player_bucket_id).all()
            player_map = {p.dg_id: p for p in bucket_players if p.dg_id}

            for api_player in live_stats:
                dg_id = api_player.get('dg_id')
                if dg_id and dg_id in player_map:
                    # The client requests the 'total' key which is score to par
                    player_map[dg_id].current_score = api_player.get('total', 0)

            db.session.commit()
            print("--- Initial scores updated successfully. ---")

    return new_league, None

# live leaderboard
@league_bp.route('/api/<int:league_id>/leaderboard')
@login_required
def get_leaderboard_data(league_id):
    # 1. Call the helper function to get the league and the final sorted list
    league, sorted_entries = _get_sorted_leaderboard(league_id)
    leaderboard_data = []

    # 2. Loop through the results from the helper function to build the JSON
    for i, entry in enumerate(sorted_entries):
        leaderboard_data.append({
            'rank': i + 1,
            'entry_name': entry.entry_name,
            'user_id': entry.user.id,
            'players': [
                {'name': entry.player1.full_name(), 'score': entry.player1.current_score, 'dg_id': entry.player1.dg_id},
                {'name': entry.player2.full_name(), 'score': entry.player2.current_score, 'dg_id': entry.player2.dg_id},
                {'name': entry.player3.full_name(), 'score': entry.player3.current_score, 'dg_id': entry.player3.dg_id},
            ],
            'total_score': entry.total_score,
            'is_current_user': entry.user_id == current_user.id
        })

    return jsonify(leaderboard_data)

@league_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_league():
    if not getattr(current_user, 'is_club_admin', False):
        flash('You do not have permission to create a league.', 'warning')
        return redirect(url_for('main.user_dashboard'))

    player_buckets = PlayerBucket.query.all()

    if request.method == 'POST':
        new_league, error = _create_new_league(
            name=request.form.get('name'),
            start_date_str=request.form.get('start_date'),
            player_bucket_id=request.form.get('player_bucket_id'),
            entry_fee_str=request.form.get('entry_fee'),
            prize_amount_str=request.form.get('prize_amount'),
            rules=request.form.get('rules'),
            prize_details=request.form.get('prize_details'),
            tie_breaker=request.form.get('tie_breaker_question'),
            tour=request.form.get('tour'),
            max_entries=request.form.get('max_entries'),
            odds_limit=request.form.get('odds_limit'),
            no_favorites_rule=request.form.get('no_favorites_rule'),
            is_public=False,
            club_creator=current_user
        )

        if error:
            flash(error, 'danger')
            return render_template('league/create_league.html', player_buckets=player_buckets, form_data=request.form)

        flash(f'League "{new_league.name}" created successfully! The league code is {new_league.league_code}.', 'success')
        return redirect(url_for('main.club_dashboard'))

    return render_template('league/create_league.html', player_buckets=player_buckets)


@league_bp.route('/create-user-league', methods=['GET', 'POST'])
@login_required
def create_user_league():
    player_buckets = PlayerBucket.query.all()

    if request.method == 'POST':
        new_league, error = _create_new_league(
            name=request.form.get('name'),
            start_date_str=request.form.get('start_date'),
            player_bucket_id=request.form.get('player_bucket_id'),
            entry_fee_str=request.form.get('entry_fee'),
            prize_amount_str=request.form.get('prize_amount'),
            rules=request.form.get('rules'),
            prize_details=request.form.get('prize_details'),
            tie_breaker=request.form.get('tie_breaker_question'),
            tour=request.form.get('tour'),
            max_entries=request.form.get('max_entries'),
            odds_limit=request.form.get('odds_limit'),
            no_favorites_rule=request.form.get('no_favorites_rule'),
            is_public=False,
            club_creator=current_user
        )
        if error:
            flash(error, 'danger')
            return render_template('league/create_user_league.html', player_buckets=player_buckets, form_data=request.form)

        flash(f'Your league "{new_league.name}" has been created! The league code is {new_league.league_code}.', 'success')
        return redirect(url_for('main.user_dashboard'))

    return render_template('league/create_user_league.html', player_buckets=player_buckets)


@league_bp.route('/join', methods=['POST'])
@login_required
def join_league():
    league_code = request.form.get('league_code').strip()

    if not league_code:
        flash('League code cannot be empty.', 'danger')
        return redirect(url_for('main.user_dashboard'))

    league = League.query.filter_by(league_code=league_code).first()

    if not league:
        flash('Invalid league code. Please check the code and try again.', 'danger')
        return redirect(url_for('main.user_dashboard'))

    existing_entry = LeagueEntry.query.filter_by(
        user_id=current_user.id,
        league_id=league.id
    ).first()

    if existing_entry:
        flash('You have already joined this league.', 'info')
        return redirect(url_for('main.user_dashboard'))

    flash(f'Successfully found league: {league.name}. Please create your entry.', 'success')
    return redirect(url_for('league.add_entry', league_id=league.id))

# ---  add_entry ROUTE ---
@league_bp.route('/add_entry/<int:league_id>', methods=['GET', 'POST'])
@login_required
def add_entry(league_id):
    league = League.query.get_or_404(league_id)

    # --- Max Entries Rule Check (for GET request) ---
    if league.max_entries and len(league.entries) >= league.max_entries:
        flash(f'This league is full and cannot accept new entries.', 'danger')
        return redirect(url_for('main.user_dashboard'))

    # --- Validation Checks (for both GET and POST) ---
    if league.has_entry_deadline_passed and not is_testing_mode_active():
        flash('The deadline for joining this league has passed.', 'danger')
        return redirect(url_for('main.user_dashboard'))

    if LeagueEntry.query.filter_by(user_id=current_user.id, league_id=league.id).first():
        flash('You have already created an entry for this league.', 'info')
        return redirect(url_for('main.user_dashboard'))

    if not league.player_bucket:
        flash('This league does not have any players associated with it yet.', 'danger')
        return redirect(url_for('main.user_dashboard'))


    # --- "No Favorites" Rule Logic ---
    players_in_bucket = league.player_bucket.players
    excluded_player_ids = set()
    if league.no_favorites_rule > 0:
        # Sort players by odds (lowest odds are favorites) and get the top N
        favorites = sorted(players_in_bucket, key=lambda p: p.odds)[:league.no_favorites_rule]
        excluded_player_ids = {p.id for p in favorites}

    # Filter the list of available players
    available_players = [p for p in players_in_bucket if p.id not in excluded_player_ids]

    # --- Handle Form Submission ---
    if request.method == 'POST':
        # ---  Max Entries Rule Check (for POST request) ---
        if league.max_entries and len(league.entries) >= league.max_entries:
            flash(f'This league has just become full. Your entry could not be submitted.', 'danger')
            return redirect(url_for('main.user_dashboard'))

        player1_id = request.form.get('player1')
        player2_id = request.form.get('player2')
        player3_id = request.form.get('player3')
        tie_breaker_answer = request.form.get('tie_breaker_answer')

        # Basic validation
        if not all([player1_id, player2_id, player3_id, tie_breaker_answer]):
            flash('Please fill out all fields.', 'danger')
            return redirect(url_for('league.add_entry', league_id=league.id))

        p1 = Player.query.get(player1_id)
        p2 = Player.query.get(player2_id)
        p3 = Player.query.get(player3_id)
        total_odds = p1.odds + p2.odds + p3.odds

        # --- Odds Cap Rule Check ---
        if league.odds_limit and total_odds > league.odds_limit:
            flash(f'The combined odds of your players ({total_odds:.2f}) exceed the league limit of {league.odds_limit}.', 'danger')
            return redirect(url_for('league.add_entry', league_id=league.id))

        # --- Payment Logic ---
        if league.entry_fee >= 5:
            session['pending_entry'] = {
                'league_id': league.id, 'player1_id': player1_id, 'player2_id': player2_id,
                'player3_id': player3_id, 'tie_breaker_answer': tie_breaker_answer, 'total_odds': total_odds
            }
            try:
                checkout_session = stripe.checkout.Session.create(
                    line_items=[{'price_data': {'currency': 'eur', 'product_data': {'name': f"Entry for {league.name}"}, 'unit_amount': int(league.entry_fee * 100)}, 'quantity': 1}],
                    mode='payment',
                    success_url=url_for('league.success', _external=True),
                    cancel_url=url_for('league.cancel', _external=True),
                )
                return redirect(checkout_session.url, code=303)
            except Exception as e:
                flash(f'Error connecting to payment gateway: {e}', 'danger')
                return redirect(url_for('league.add_entry', league_id=league.id))
        else: # Free entry
            new_entry = LeagueEntry(
                entry_name=current_user.full_name, total_odds=total_odds,
                tie_breaker_answer=int(tie_breaker_answer), league_id=league.id, user_id=current_user.id,
                player1_id=p1.id, player2_id=p2.id, player3_id=p3.id
            )
            db.session.add(new_entry)
            db.session.commit()

            # Send confirmation email
            send_entry_confirmation_email(current_user, league)

            flash('Your free entry has been successfully submitted!', 'success')
            return redirect(url_for('main.user_dashboard'))

    # --- Handle Page Load (GET Request) ---
    return render_template('league/add_entry.html', league=league, players=available_players)



@league_bp.route('/edit_entry/<int:entry_id>', methods=['GET', 'POST'])
@login_required
def edit_entry(entry_id):
    entry = LeagueEntry.query.get_or_404(entry_id)
    league = entry.league

    if entry.user_id != current_user.id:
        flash('You do not have permission to edit this entry.', 'danger')
        return redirect(url_for('main.user_dashboard'))

    if league.has_entry_deadline_passed and not is_testing_mode_active():
        flash('The deadline for editing entries in this league has passed.', 'danger')
        return redirect(url_for('league.view_league', league_id=league.id))

    # --- "No Favorites" Rule Logic ---
    players_in_bucket = league.player_bucket.players
    excluded_player_ids = set()
    if league.no_favorites_rule > 0:
        # Sort players by odds (lowest odds are favorites) and get the top N
        favorites = sorted(players_in_bucket, key=lambda p: p.odds)[:league.no_favorites_rule]
        excluded_player_ids = {p.id for p in favorites}

    # Filter the list of available players
    available_players = [p for p in players_in_bucket if p.id not in excluded_player_ids]

    if request.method == 'POST':
        player1_id = request.form.get('player1')
        player2_id = request.form.get('player2')
        player3_id = request.form.get('player3')
        tie_breaker_answer = request.form.get('tie_breaker_answer')

        selected_ids = {player1_id, player2_id, player3_id}
        if None in selected_ids or '' in selected_ids or len(selected_ids) != 3:
            flash('You must select three different players.', 'danger')
            return redirect(url_for('league.edit_entry', entry_id=entry.id))

        if not tie_breaker_answer or not tie_breaker_answer.isdigit():
            flash('You must provide a valid number for the tie-breaker.', 'danger')
            return redirect(url_for('league.edit_entry', entry_id=entry.id))

        p1 = Player.query.get(player1_id)
        p2 = Player.query.get(player2_id)
        p3 = Player.query.get(player3_id)
        total_odds = p1.odds + p2.odds + p3.odds

        # --- Odds Cap Rule Check ---
        if league.odds_limit and total_odds > league.odds_limit:
            flash(f'The combined odds of your players ({total_odds:.2f}) exceed the league limit of {league.odds_limit}.', 'danger')
            return redirect(url_for('league.edit_entry', entry_id=entry.id))

        if total_odds < 100:
            flash('The combined odds of your selected players must be at least 100.', 'danger')
            return redirect(url_for('league.edit_entry', entry_id=entry.id))

        entry.player1_id = p1.id
        entry.player2_id = p2.id
        entry.player3_id = p3.id
        entry.total_odds = total_odds
        entry.tie_breaker_answer = int(tie_breaker_answer)

        db.session.commit()
        flash('Your entry has been successfully updated!', 'success')
        return redirect(url_for('main.user_dashboard'))

    return render_template('league/edit_entry.html', league=league, players=available_players, entry=entry)


# --- Stripe Success and Cancel Routes ---
@league_bp.route('/success')
@login_required
def success():
    pending_entry_data = session.pop('pending_entry', None)
    if not pending_entry_data:
        flash('Your session expired after payment. Please try creating your entry again.', 'danger')
        return redirect(url_for('main.user_dashboard'))

    # 2. Safely get all required data using .get() to avoid KeyErrors
    league_id = pending_entry_data.get('league_id')
    player1_id = pending_entry_data.get('player1_id')
    player2_id = pending_entry_data.get('player2_id')
    player3_id = pending_entry_data.get('player3_id')
    tie_breaker_str = pending_entry_data.get('tie_breaker_answer')
    total_odds = pending_entry_data.get('total_odds')

     # 3. Check if any essential data is missing
    if not all([league_id, player1_id, player2_id, player3_id, tie_breaker_str, total_odds is not None]):
        flash('Incomplete entry data was found after payment. Please try again.', 'danger')
        return redirect(url_for('main.user_dashboard'))

    # 5. Use a try-except block for type conversion
    try:
        tie_breaker_answer = int(tie_breaker_str)
    except (ValueError, TypeError):
        flash('Invalid tie-breaker format found after payment. Please try again.', 'danger')
        return redirect(url_for('main.user_dashboard'))


    # If all checks pass, create the new entry
    new_entry = LeagueEntry(
        entry_name=current_user.full_name,
        total_odds=total_odds,
        tie_breaker_answer=tie_breaker_answer,
        league_id=league_id,
        user_id=current_user.id,
        player1_id=player1_id,
        player2_id=player2_id,
        player3_id=player3_id
    )

    db.session.add(new_entry)
    db.session.commit()

    # Send confirmation email
    league = League.query.get(new_entry.league_id)
    send_entry_confirmation_email(current_user, league)

    flash('Payment successful! Your entry has been submitted.', 'success')
    return render_template('league/success.html')

@league_bp.route('/cancel')
@login_required
def cancel():
    session.pop('pending_entry', None)
    return render_template('league/cancel.html')

@league_bp.route('/<int:league_id>')
@login_required
def view_league(league_id):
    # --- MODIFIED ---
    # Call the helper function to get the league object and sorted entries
    league, sorted_entries = _get_sorted_leaderboard(league_id)

    # Find the current user's entry to highlight it in the template
    current_user_entry = LeagueEntry.query.filter_by(league_id=league.id, user_id=current_user.id).first()

    return render_template('league/view_league.html', league=league, entries=sorted_entries, current_user_entry=current_user_entry)


# --- Route for Admins to Trigger a Payout ---
@league_bp.route('/manage/<int:league_id>/payout', methods=['POST'])
@login_required
def mark_as_paid(league_id):
    league = League.query.get_or_404(league_id)
    winner = league.winner

    is_creator = (getattr(current_user, 'is_club_admin', False) and league.club_id == current_user.id) or \
                 (getattr(current_user, 'is_site_admin', False))

    if not is_creator:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('main.index'))

    if not league.is_finalized or not winner:
        flash('This league is not finalized or has no winner.', 'warning')
        return redirect(url_for('league.manage_league', league_id=league.id))

    if league.payout_status == 'paid':
        flash('This league has already been paid out.', 'info')
        return redirect(url_for('league.manage_league', league_id=league.id))

    if not winner.stripe_account_id:
        flash(f'The winner, {winner.full_name}, has not set up their payout account yet.', 'danger')
        return redirect(url_for('league.manage_league', league_id=league.id))

    prize_amount = league.prize_amount

    if prize_amount > 0:
        try:
            stripe.Transfer.create(
                amount=int(prize_amount * 100),  # Use the fixed prize_amount
                currency="eur",
                destination=winner.stripe_account_id,
                description=f"Prize for winning the league: {league.name}"
            )
        except Exception as e:
            flash(f"Stripe Error: Could not process payout. {str(e)}", 'danger')
            return redirect(url_for('league.manage_league', league_id=league.id))

    # Update database records
    winner.total_winnings = (winner.total_winnings or 0.0) + prize_amount
    league.payout_status = 'paid'
    db.session.commit()

    flash(f"Successfully paid out €{prize_amount:.2f} to {winner.full_name} and marked league as paid.", 'success')
    return redirect(url_for('league.manage_league', league_id=league.id))



@league_bp.route('/manage/<int:league_id>')
@login_required
def manage_league(league_id):
    league = League.query.get_or_404(league_id)

    # Security Check: Ensure the logged-in user is a club admin and owns this league
    if not getattr(current_user, 'is_club_admin', False) or league.club_id != current_user.id:
        flash('You do not have permission to manage this league.', 'danger')
        return redirect(url_for('main.club_dashboard'))

    # Get all entries for this league, eager loading the user and player details
    entries = LeagueEntry.query.filter_by(league_id=league.id).options(
        db.joinedload(LeagueEntry.user),
        db.joinedload(LeagueEntry.player1),
        db.joinedload(LeagueEntry.player2),
        db.joinedload(LeagueEntry.player3)
    ).all()

    return render_template('league/manage_league.html', league=league, entries=entries)


@league_bp.route('/finalize/<int:league_id>', methods=['POST'])
@login_required
def finalize_league(league_id):
    league = League.query.get_or_404(league_id)

    if not getattr(current_user, 'is_club_admin', False) or league.club_id != current_user.id:
        flash('You do not have permission to finalize this league.', 'danger')
        return redirect(url_for('main.club_dashboard'))

    if not league.has_ended:
        flash('This league cannot be finalized until the tournament is over.', 'warning')
        return redirect(url_for('league.manage_league', league_id=league.id))

    if league.is_finalized:
        flash('This league has already been finalized.', 'info')
        return redirect(url_for('league.manage_league', league_id=league.id))

    actual_answer_str = request.form.get('tie_breaker_actual_answer')
    if not actual_answer_str or not actual_answer_str.isdigit():
        flash('You must provide a valid number for the tie-breaker answer.', 'danger')
        return redirect(url_for('league.manage_league', league_id=league.id))

    actual_answer = int(actual_answer_str)

    entries = league.entries
    if not entries:
        flash('Cannot finalize a league with no entries.', 'warning')
        return redirect(url_for('league.manage_league', league_id=league.id))

    for entry in entries:
        entry.total_score = entry.player1.current_score + entry.player2.current_score + entry.player3.current_score

    min_score = min(entry.total_score for entry in entries)
    top_entries = [entry for entry in entries if entry.total_score == min_score]

    winner = None
    if len(top_entries) == 1:
        winner = top_entries[0].user
    else:
        winner_entry = min(top_entries, key=lambda x: abs(x.tie_breaker_answer - actual_answer))
        winner = winner_entry.user

    league.is_finalized = True
    league.tie_breaker_actual_answer = actual_answer
    league.winner_id = winner.id
    db.session.commit()

    # Send winner notification email to all participants
    send_winner_notification_email(league)

    flash(f'League finalized! The winner is {winner.full_name}.', 'success')
    return redirect(url_for('league.view_league', league_id=league.id))


@league_bp.route('/delete/<int:league_id>', methods=['POST'])
@login_required
def delete_league(league_id):
    league = League.query.get_or_404(league_id)

    if not getattr(current_user, 'is_club_admin', False) or league.club_id != current_user.id:
        flash('You do not have permission to delete this league.', 'danger')
        return redirect(url_for('main.club_dashboard'))

    if league.entries and not league.has_ended:
        flash('This league cannot be deleted because it has active entries and has not finished yet.', 'danger')
        return redirect(url_for('league.manage_league', league_id=league.id))

    try:
        LeagueEntry.query.filter_by(league_id=league.id).delete()
        db.session.delete(league)
        db.session.commit()
        flash(f'The league "{league.name}" and all its entries have been permanently deleted.', 'success')
        return redirect(url_for('main.club_dashboard'))

    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while trying to delete the league: {e}', 'danger')
        return redirect(url_for('league.manage_league', league_id=league.id))



# --- email helper functions ---
def send_entry_confirmation_email(user, league):
    """Sends an email to a user confirming their league entry."""
    msg = Message('League Entry Confirmation',
                  sender=current_app.config['MAIL_DEFAULT_SENDER'],
                  recipients=[user.email])
    msg.body = f"""Hi {user.full_name},

This email confirms your entry into the league: "{league.name}".

The entry deadline is {league.entry_deadline.strftime('%d %b %Y at %H:%M')} UTC. You can edit your entry until this time.

Good luck!
"""
    mail.send(msg)

def send_winner_notification_email(league):
    """Sends an email to all participants announcing the winner."""
    winner = league.winner
    if not winner:
        return

    # Get all participants' emails
    recipients = [entry.user.email for entry in league.entries]

    msg = Message(f'The Winner of "{league.name}" has been announced!',
                  sender=current_app.config['MAIL_DEFAULT_SENDER'],
                  recipients=recipients)
    msg.body = f"""The results are in for the league: "{league.name}"!

The winner is: {winner.full_name}

Congratulations to the winner and thank you to everyone who participated.
"""
    mail.send(msg)