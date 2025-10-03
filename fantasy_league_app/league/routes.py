from flask_mail import Message
from flask import render_template, redirect, url_for, flash, request, session, current_app, jsonify
from flask_login import login_required, current_user
from fantasy_league_app import db, mail
from ..models import User, Club, SiteAdmin, League, LeagueEntry, Player, PlayerBucket, PlayerScore
from ..utils import is_testing_mode_active, send_entry_confirmation_email, send_winner_notification_email
from . import league_bp
import json
import random
import string
import stripe
from datetime import datetime, timedelta
from ..data_golf_client import DataGolfClient
from ..stripe_client import process_payouts
import secrets
from ..forms import LeagueForm, CreateUserLeagueForm, EditLeagueForm
from ..utils import get_league_creation_status
from ..auth.decorators import admin_required, user_required
from fantasy_league_app.cache_utils import CacheManager, cache_result
from ..main.routes import (
    calculate_user_stats,
    get_enhanced_league_history,
    get_recent_activity
)



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

def _create_new_league(name, player_bucket_id, entry_fee_str,
                         prize_amount_str, max_entries, odds_limit, rules,
                         prize_details, no_favorites_rule, tour, is_public, creator_id,
                         club_id=None, allow_past_creation=False):
    """
    A helper function to handle the creation of any type of league.
    Returns (new_league, error_message)
    """

    # --- Automatic Date Calculation Logic ---
    today = datetime.utcnow()

    if tour == 'alt': # LIV Tournaments start on Friday
        target_weekday = 4 # Friday
        end_day_delta = 2 # Ends on Sunday
    else: # PGA, Euro, KFT start on Thursday
        target_weekday = 3 # Thursday
        end_day_delta = 3 # Ends on Sunday

    days_until_target = (target_weekday - today.weekday() + 7) % 7
    if days_until_target == 0: # If today is the target day, schedule for next week
        days_until_target = 7

    start_date = (today + timedelta(days=days_until_target)).replace(hour=6, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=end_day_delta)
    entry_deadline=start_date - timedelta(hours=12)
    # --- End of Date Logic ---

    # --- Validation ---
    try:
        entry_fee = float(entry_fee_str)
        prize_amount = int(prize_amount_str)
        user_id = current_user.id
        start_date = start_date
        max_entries_val = int(max_entries) if max_entries else None
        odds_limit_val = int(odds_limit) if odds_limit else None
    except (ValueError, TypeError):
        return None, "Invalid date, fee, or prize format."

    if League.query.filter_by(name=name).first():
        return None, f"A league with the name '{name}' already exists. Please choose a different name."

    if not allow_past_creation and start_date < datetime.utcnow() + timedelta(days=1):
        return None, "The tournament start date must be at least 1 days in the future."

    if 0 < entry_fee < 5:
        return None, "The entry fee must be €0.00 or at least €5.00."

    # --- Logic ---
    end_date = start_date + timedelta(days=4)
    league_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    while League.query.filter_by(league_code=league_code).first():
        league_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


    bucket = PlayerBucket.query.get(player_bucket_id)
    if not bucket:
        return None, "Selected player pool not found."

    tie_breaker_player = bucket.get_random_player_for_tie_breaker()
    if not tie_breaker_player:
        return None, "Cannot create league: The selected player pool is empty."

    # Generate the question and store the player's ID
    tie_breaker_question = f"What will be the final stroke count for {tie_breaker_player.full_name()}'s on Day 2 of the tournament be?"
    tie_breaker_player_id = tie_breaker_player.dg_id


    # user_id = None
    # site_admin_id = None
    # club_id = None

    # # Check the type of the logged-in user
    # if isinstance(current_user, User):
    #     user_id = current_user.id
    # elif isinstance(current_user, SiteAdmin):
    #     site_admin_id = current_user.id
    # elif isinstance(current_user, Club):
    #     club_id = current_user.id
    # else:
    #     return None, "Invalid user type for league creation."

    # 1. Generate a unique league code BEFORE creating the league object.
    while True:
        alphabet = string.ascii_uppercase + string.digits
        # Using 8 characters for better uniqueness
        league_code = ''.join(secrets.choice(alphabet) for _ in range(8))
        if not League.query.filter_by(league_code=league_code).first():
            # The code is unique, we can proceed.
            break

    new_league = League(
        name=name,
        league_code=league_code,
        start_date=start_date,
        end_date=end_date,
        player_bucket_id=player_bucket_id,
        entry_fee=entry_fee,
        prize_amount=prize_amount,
        max_entries=max_entries,
        odds_limit=odds_limit,
        entry_deadline=entry_deadline,
        rules=rules,
        prize_details=prize_details,
        no_favorites_rule=no_favorites_rule,
        tour=tour,
        tie_breaker_question=tie_breaker_question,
        is_public=is_public,
        club_id=club_id,
        creator_id=creator_id,
        user_id=user_id
    )
    db.session.add(new_league)
    db.session.commit()

    # --- Fetch initial scores using the client ---
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
    """Cached leaderboard API endpoint"""
    league = League.query.get_or_404(league_id)

    # Use the cached leaderboard method from the model
    leaderboard_data = league.get_leaderboard_()

    # Add user-specific data
    for entry in leaderboard_data:
        entry['is_current_user'] = entry.get('user_id') == current_user.id

    return jsonify(leaderboard_data)
# def get_leaderboard_data(league_id):
#     # 1. Call the helper function to get the league and the final sorted list
#     league, sorted_entries = _get_sorted_leaderboard(league_id)
#     leaderboard_data = []

#     # 2. Loop through the results from the helper function to build the JSON
#     for i, entry in enumerate(sorted_entries):
#         leaderboard_data.append({
#             'rank': i + 1,
#             'entry_name': entry.entry_name,
#             'user_id': entry.user.id,
#             'players': [
#                 {'name': entry.player1.full_name(), 'score': entry.player1.current_score, 'dg_id': entry.player1.dg_id},
#                 {'name': entry.player2.full_name(), 'score': entry.player2.current_score, 'dg_id': entry.player2.dg_id},
#                 {'name': entry.player3.full_name(), 'score': entry.player3.current_score, 'dg_id': entry.player3.dg_id},
#             ],
#             'total_score': entry.total_score,
#             'is_current_user': entry.user_id == current_user.id
#         })

#     return jsonify(leaderboard_data)

@league_bp.route('/create-league', methods=['GET', 'POST'])
@login_required
def create_league():
    if not getattr(current_user, 'is_club_admin', False):
        flash('You do not have permission to create a league.', 'warning')
        return redirect(url_for('main.user_dashboard'))

    # status = get_league_creation_status()
    # if not status["is_creation_enabled"]:
    #     flash(status["message"], "warning")
    #     return redirect(url_for('main.club_dashboard'))

    form = LeagueForm()
    # form.player_bucket_id.choices = [
    #     (b.id, b.name) for b in PlayerBucket.query.filter(PlayerBucket.tour.in_(status["available_tours"])).order_by('name').all()
    # ]

    available_buckets = PlayerBucket.query.order_by(PlayerBucket.name).all()
    # Create a list of (value, label) tuples for the dropdown choices
    form.player_bucket_id.choices = [(0, 'Select a Player Pool')] + [(bucket.id, bucket.name) for bucket in available_buckets]

    if form.validate_on_submit():
        if form.player_bucket_id.data == 0:
            flash('Please select a valid player pool.', 'danger')
            return render_template('league/create_league.html', form=form)
        new_league, error = _create_new_league(
            name=form.name.data,
            player_bucket_id=form.player_bucket_id.data,
            entry_fee_str=str(form.entry_fee.data),
            prize_amount_str=str(form.prize_amount.data),
            max_entries=form.max_entries.data,
            odds_limit=form.odds_limit.data,
            rules=form.rules.data,
            prize_details=form.prize_details.data,
            no_favorites_rule=form.no_favorites_rule.data,
            tour=form.tour.data,
            is_public=False, # Club leagues are not public
            creator_id=current_user.id,
            club_id=current_user.id # Pass the club_id
        )
        pass

        if error:
            flash(error, 'danger')
        else:
            flash(f'League "{new_league.name}" created successfully! The league code is {new_league.league_code}.', 'success')
            return redirect(url_for('main.club_dashboard'))

    return render_template('league/create_league.html', form=form)

@league_bp.route('/edit-league/<int:league_id>', methods=['GET', 'POST'])
@user_required
def edit_league(league_id):
    """
    Allows a club admin to edit the details of an upcoming league they created.
    """
    league = League.query.get_or_404(league_id)
    now = datetime.utcnow()

    # Security Checks
    if not isinstance(current_user, Club) or league.club_id != current_user.id:
        flash("You do not have permission to edit this league.", "danger")
        return redirect(url_for('main.club_dashboard'))

    if league.start_date <= now:
        flash("You can only edit leagues that have not started yet.", "warning")
        return redirect(url_for('main.club_dashboard'))

    form = EditLeagueForm(obj=league) # Pre-populate form with league data

    if form.validate_on_submit():
        # Update the league object with form data
        league.name = form.name.data
        league.entry_fee = form.entry_fee.data
        league.prize_details = form.prize_details.data
        league.rules = form.rules.data
        db.session.commit()
        flash(f"'{league.name}' has been updated successfully!", "success")
        return redirect(url_for('main.club_dashboard'))

    return render_template('league/edit_league.html', form=form, league=league, title="Edit League")

@league_bp.route('/cancel-league/<int:league_id>', methods=['POST'])
@user_required
def cancel_league(league_id):
    league = League.query.get_or_404(league_id)
    now = datetime.utcnow()

    # Security Checks
    if not isinstance(current_user, Club) or league.club_id != current_user.id:
        flash("You do not have permission to cancel this league.", "danger")
        return redirect(url_for('main.club_dashboard'))

    if league.start_date <= now:
        flash("You can only cancel leagues that have not started yet.", "warning")
        return redirect(url_for('main.club_dashboard'))

    try:
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
        refund_count = 0

        # Find all paid entries and issue refunds
        for entry in league.entries:
            if entry.payment_intent_id:
                stripe.Refund.create(
                    payment_intent=entry.payment_intent_id,
                    # Refund on the connected account
                    stripe_account=current_user.stripe_account_id
                )
                refund_count += 1

        # After refunds, delete the league and its entries
        # The cascade delete should handle entries automatically
        db.session.delete(league)
        db.session.commit()

        flash(f"'{league.name}' has been successfully canceled. {refund_count} refund(s) processed.", "success")

    except stripe.error.StripeError as e:
        flash(f"A Stripe error occurred: {e}. League was not canceled.", "danger")
    except Exception as e:
        flash(f"An unexpected error occurred: {e}. League was not canceled.", "danger")

    return redirect(url_for('main.club_dashboard'))

@league_bp.route('/get-tour-for-bucket/<int:bucket_id>')
@login_required
def get_tour_for_bucket(bucket_id):
    """
    API endpoint to fetch the tour associated with a specific PlayerBucket.
    """
    bucket = PlayerBucket.query.get(bucket_id)
    if bucket:
        # Return the tour as a JSON object
        return jsonify({'tour': bucket.tour})

    # Return an error if the bucket is not found
    return jsonify({'error': 'Player bucket not found'}), 404


@league_bp.route('/create-user-league', methods=['GET', 'POST'])
@login_required
def create_user_league():
    # form = CreateUserLeagueForm()
    player_buckets = PlayerBucket.query.all()

    # if form.validate_on_submit():
    #     # --- START: Dynamically Generate Rules and Prizes ---

    #     # 1. Generate Rules Text
    #     rules_text = "Select 3 players from the player pool to compete for top prize. The lowest combined score wins. If there is a tie break, the users closest to the winning tie break answer will split the prize pool."
    #     if form.no_favorites.data:
    #         rules_text += " The top 5 players from this tournament cannot be selected."

    #     # 2. Generate Prizes Text
    #     prizes_text = f"This league has a {form.prize_pool_percentage.data}% share of the entries pool. The entries pool is 75% of the total revenue generated by a league."

    #     # --- END: Generation Logic ---

    if request.method == 'POST':
        new_league, error = _create_new_league(
            name=request.form.get('name'),
            # start_date_str=start_date,
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
            creator_id=current_user.id,
            club_id=current_user
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
    # 1. Get the incoming data as JSON
    data = request.get_json()

    # 2. Check if the data or the code is missing
    if not data or 'league_code' not in data:
        return jsonify({'error': 'Missing league code.'}), 400

    league_code = data.get('league_code', '').strip()

    if not league_code:
        return jsonify({'error': 'League code cannot be empty.'}), 400

    # 3. Find the league
    league = League.query.filter_by(league_code=league_code).first()

    if not league:
        # Return a JSON error if the league is not found
        return jsonify({'error': 'Invalid league code. Please check the code and try again.'}), 404

    # 4. Check if the user is already in the league
    existing_entry = LeagueEntry.query.filter_by(
        user_id=current_user.id,
        league_id=league.id
    ).first()

    if existing_entry:
        # Return a JSON error for a conflict
        return jsonify({'error': 'You have already joined this league.'}), 409

    # 5. Return a successful JSON response
    # The final redirect will be handled by the JavaScript
    return jsonify({
        'message': f'Successfully found league: {league.name}. Please create your entry.',
        'redirect_url': url_for('league.add_entry', league_id=league.id)
    }), 200
    # league_code = request.form.get('league-code').strip()

    # if not league_code:
    #     flash('League code cannot be empty.', 'danger')
    #     return redirect(url_for('main.user_dashboard'))

    # league = League.query.filter_by(league_code=league_code).first()

    # if not league:
    #     flash('Invalid league code. Please check the code and try again.', 'danger')
    #     return redirect(url_for('main.user_dashboard'))

    # existing_entry = LeagueEntry.query.filter_by(
    #     user_id=current_user.id,
    #     league_id=league.id
    # ).first()

    # if existing_entry:
    #     flash('You have already joined this league.', 'info')
    #     return redirect(url_for('main.user_dashboard'))

    # flash(f'Successfully found league: {league.name}. Please create your entry.', 'success')
    # return redirect(url_for('league.add_entry', league_id=league.id))

# ---  add_entry ROUTE ---
@league_bp.route('/add_entry/<int:league_id>', methods=['GET', 'POST'], strict_slashes=False)
@login_required
def add_entry(league_id):
    """
    Allows a user to create a new entry for a specific league.
    """
    print(f"DEBUG: add_entry called with league_id={league_id}")
    print(f"DEBUG: current_user={current_user}")
    print(f"DEBUG: is_site_admin={getattr(current_user, 'is_site_admin', False)}")

    if getattr(current_user, 'is_site_admin', False):
        flash("Site admins cannot join leagues.", "danger")
        return redirect(url_for('admin.admin_dashboard'))

    print(f"DEBUG: About to query league {league_id}")
    league = League.query.get_or_404(league_id)
    print(f"DEBUG: League found: {league.name}")

    print(f"DEBUG: Checking max entries...")
    if league.max_entries and len(league.entries) >= league.max_entries:
        print(f"DEBUG: League is full")
        flash(f'This league is full and cannot accept new entries.', 'danger')
        return redirect(url_for('main.user_dashboard'))

    print(f"DEBUG: Checking deadline...")
    if league.has_entry_deadline_passed and not is_testing_mode_active():
        print(f"DEBUG: Deadline has passed")
        flash('The deadline for joining this league has passed.', 'danger')
        return redirect(url_for('main.user_dashboard'))

    print(f"DEBUG: Checking existing entry...")
    existing = LeagueEntry.query.filter_by(user_id=current_user.id, league_id=league.id).first()
    if existing:
        print(f"DEBUG: User already has entry")
        flash('You have already created an entry for this league.', 'info')
        return redirect(url_for('main.user_dashboard'))

    print(f"DEBUG: Checking player bucket...")
    if not league.player_bucket:
        print(f"DEBUG: No player bucket found")
        flash('This league does not have any players associated with it yet.', 'danger')
        return redirect(url_for('main.user_dashboard'))

    print(f"DEBUG: All checks passed, preparing to render template...")



    # league = League.query.get_or_404(league_id)

    #  # Check if the user has connected a Stripe account at all.
    # if not club.stripe_account_id:
    #     flash('Connect your stripe details from the "My Profile" section', 'error')
    #     return redirect(url_for('main.user_dashboard'))

    # try:
    #     # Check the status of the connected account directly with the Stripe API
    #     account = stripe.Account.retrieve(current_user.stripe_account_id)
    #     # 'transfers_enabled' is the key field that confirms they can receive payouts.
    #     if not account.details_submitted or not account.transfers_enabled:
    #         flash('Your Stripe account is currently not able to receive transfers. Please edit your stripe details from the My Profile section in your dashboard.', 'error')
    #         return redirect(url_for('main.user_dashboard'))
    # except Exception as e:
    #     # If there's an error retrieving the account (e.g., it's invalid), block entry.
    #     current_app.logger.error(f"Stripe API error for user {current_user.id}: {e}")
    #     flash('stripe_error', 'error')
    #     return redirect(url_for('main.user_dashboard'))

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

    # The application fee in cents (€2.50 = 250 cents)
    application_fee = 250

    # The entry fee in cents
    entry_fee_cents = int(league.entry_fee * 100)

    print(f"DEBUG: LEAGUE ID: {league.club_id}")

    if league.club_id:
        club = Club.query.get_or_404(league.club_id)
    else:
        club = None


    # --- "No Favorites" Rule Logic ---
    players_in_bucket = league.player_bucket.players
    excluded_player_ids = set()
    if league.no_favorites_rule > 0:
        # Sort players by odds (lowest odds are favorites) and get the top N
        favorites = sorted(players_in_bucket, key=lambda p: p.odds)[:league.no_favorites_rule]
        excluded_player_ids = {p.id for p in favorites}


    # Fetch and prepare player data for the template's JavaScript
    players_from_bucket = sorted(league.player_bucket.players, key=lambda p: p.odds)
    available_players = [
        {"id": p.id, "name": p.name, "surname": p.surname, "odds": p.odds}
        for p in players_from_bucket
    ]

    # --- Handle Form Submission ---
    if request.method == 'POST':
        # ---  Max Entries Rule Check (for POST request) ---
        if league.max_entries and len(league.entries) >= league.max_entries:
            flash(f'This league has just become full. Your entry could not be submitted.', 'danger')
            return redirect(url_for('main.user_dashboard'))

        player1_id = request.form.get('player1_id')
        player2_id = request.form.get('player2_id')
        player3_id = request.form.get('player3_id')
        tie_breaker_answer = request.form.get('tie_breaker_answer')

        # --- Validation Logic (same as edit_entry) ---
        if not all([player1_id, player2_id, player3_id]):
            flash('Your team must have three players selected.', 'danger')
            return redirect(url_for('league.add_entry', league_id=league_id))

        p1 = Player.query.get(player1_id)
        p2 = Player.query.get(player2_id)
        p3 = Player.query.get(player3_id)
        total_odds = p1.odds + p2.odds + p3.odds

         # --- Odds Cap Rule Check ---
        if league.odds_limit and total_odds < league.odds_limit:
            flash(f'The combined total of your players ({total_odds:.2f}) do not meet the minimum total of {league.odds_limit}.', 'danger')
            return redirect(url_for('league.edit_entry', entry_id=entry.id))

        # --- Payment Logic ---
        if league.entry_fee >= 5:
            session['pending_entry'] = {
                'league_id': league.id, 'player1_id': player1_id, 'player2_id': player2_id,
                'player3_id': player3_id, 'tie_breaker_answer': tie_breaker_answer, 'total_odds': total_odds
            }
            try:
                # checkout_session = stripe.checkout.Session.create(
                #     line_items=[{'price_data': {'currency': 'eur', 'product_data': {'name': f"Entry for {league.name}"}, 'unit_amount': entry_fee_cents}, 'quantity': 1}],
                #     mode='payment',
                #     success_url=url_for('league.success', _external=True),
                #     cancel_url=url_for('league.cancel', _external=True),
                #     payment_intent_data={
                #         'application_fee_amount': application_fee,
                #         'transfer_data': {
                #             'destination': club.stripe_account_id,
                #         },
                #     },
                # )

                stripe.api_key = current_app.config['STRIPE_SECRET_KEY']

                if club and club.stripe_account_id:
                    # Use club's connected account
                    stripe_account = club.stripe_account_id
                else:
                    # Use platform account for admin leagues
                    stripe_account = None

                checkout_session = stripe.checkout.Session.create(
                    line_items=[{
                        'price_data': {
                            'currency': 'eur',
                            'product_data': {'name': f"Entry for {league.name}"},
                            'unit_amount': entry_fee_cents
                        },
                        'quantity': 1
                    }],
                    mode='payment',
                    success_url=url_for('league.success', _external=True),
                    cancel_url=url_for('league.cancel', _external=True),
                    stripe_account=stripe_account

                )
                return redirect(checkout_session.url, code=303)
            except Exception as e:
                flash(f'Error connecting to payment gateway: {e}', 'danger')
                return redirect(url_for('league.add_entry', league_id=league.id))
        else: # Free entry
            new_entry = LeagueEntry(
            entry_name=f"{current_user.full_name}'s Entry",
            total_odds=total_odds,
            tie_breaker_answer=tie_breaker_answer,
            league_id=league.id,
            user_id=current_user.id, # This is the crucial line
            player1_id=player1_id,
            player2_id=player2_id,
            player3_id=player3_id
        )
            db.session.add(new_entry)
            db.session.commit()


            # Send confirmation email
            # send_entry_confirmation_email(current_user, league)

            flash('Your free entry has been successfully submitted!', 'success')
            return redirect(url_for('main.user_dashboard'))

    empty_entry = {'player1': None, 'player2': None, 'player3': None, 'tie_breaker_answer': ''}

    # --- Handle Page Load (GET Request) ---
    return render_template('league/add_entry.html', league=league, title="Create Your Entry",
        entry=empty_entry, available_players=available_players)



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
    if  league.no_favorites_rule > 0:
        # Sort players by odds (lowest odds are favorites) and get the top N
        favorites = sorted(players_in_bucket, key=lambda p: p.odds)[:league.no_favorites_rule]
        excluded_player_ids = {p.id for p in favorites}

    # Fetch all players from the league's bucket
    players_from_bucket = sorted(league.player_bucket.players, key=lambda p: p.odds)

    # Filter the list of available players
    available_players = [
        {
            "id": player.id,
            "name": player.name,
            "surname": player.surname,
            "odds": player.odds
        }
        for player in players_from_bucket
    ]

    if request.method == 'POST':
        player1_id = request.form.get('player1_id')
        player2_id = request.form.get('player2_id')
        player3_id = request.form.get('player3_id')
        tie_breaker_answer = request.form.get('tie_breaker_answer')

        # 1. Check if all three player slots are filled.
        if not all([player1_id, player2_id, player3_id]):
            flash('Your team must have three players selected.', 'danger')
            return redirect(url_for('league.edit_entry', entry_id=entry_id))

        # 2. Check if the three selected players are unique from each other.
        selected_ids = {player1_id, player2_id, player3_id}
        if len(selected_ids) < 3:
            flash('You must select three different players. You cannot have duplicates in your team.', 'danger')
            return redirect(url_for('league.edit_entry', entry_id=entry_id))

        p1 = Player.query.get(player1_id)
        p2 = Player.query.get(player2_id)
        p3 = Player.query.get(player3_id)
        total_odds = p1.odds + p2.odds + p3.odds

        # --- Odds Cap Rule Check ---
        if league.odds_limit and total_odds < league.odds_limit:
            flash(f'The combined total of your players ({total_odds:.2f}) do not meet the minimum total of {league.odds_limit}.', 'danger')
            return redirect(url_for('league.edit_entry', entry_id=entry.id))

        if total_odds < 100:
            flash('The combined odds of your selected players must be at least 100.', 'danger')
            return redirect(url_for('league.edit_entry', entry_id=entry.id))


        entry.player1_id = p1.id
        entry.player2_id = p2.id
        entry.player3_id = p3.id
        entry.total_odds = total_odds
        entry.tie_breaker_answer = int(tie_breaker_answer)

        if tie_breaker_answer:
            try:
                entry.tie_breaker_answer = int(tie_breaker_answer)
            except ValueError:
                flash('Invalid tie-breaker answer. Please enter a number.', 'danger')
                return redirect(url_for('league.edit_entry', entry_id=entry_id))

        db.session.commit()
        flash('Your entry has been successfully updated!', 'success')
        return redirect(url_for('main.user_dashboard'))

    return render_template('league/edit_entry.html', league=league, available_players=available_players, entry=entry)


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

@league_bp.route('/view/<int:league_id>')
@login_required
def view_league(league_id):
    league = League.query.get_or_404(league_id)

    try:
        # Use cached leaderboard
        leaderboard = league.get_leaderboard_()
    except Exception as e:
        leaderboard = []

    for item in leaderboard:
        print(f"DEBUG: Item user_id: {item.get('user_id')}, user_name: {item.get('user_name')}")

    # Find current user's entry in the cached data
    current_user_entry = None
    user_entry_data = next(
        (item for item in leaderboard if item.get('user_id') == current_user.id),
        None
    )

    if user_entry_data:
        # Get the actual entry object for the "My Team" section
        entry_obj = LeagueEntry.query.get(user_entry_data['entry_id'])
        current_user_entry = {
            'entry': entry_obj,
            'total_score': user_entry_data['total_score'],
            'player1_score': user_entry_data['players'][0]['score'],
            'player2_score': user_entry_data['players'][1]['score'],
            'player3_score': user_entry_data['players'][2]['score']
        }
        print(f"DEBUG: Created current_user_entry: {current_user_entry}")

    profile_stats = calculate_user_stats(current_user.id)
    league_history = get_enhanced_league_history(current_user.id)
    recent_activity = get_recent_activity(current_user.id)

    return render_template('league/view_league.html',
                         league=league,
                         leaderboard=leaderboard,
                         user_entry=current_user_entry,
                         now=datetime.utcnow(),
                         user=current_user,
                         stats=profile_stats,
                         league_history=league_history,
                         recent_activity=recent_activity,
                         is_own_profile=True)
# def view_league(league_id):
#     """
#     API endpoint that returns all data needed for the league view as JSON.
#     """
#     league = League.query.get_or_404(league_id)
#     entries = LeagueEntry.query.filter_by(league_id=league.id).all()

#     leaderboard = []

#     if league.is_finalized:
#         # --- LOGIC FOR FINALIZED LEAGUES (Your existing code) ---
#         print("League is finalized. Fetching historical scores.")
#         historical_scores = {hs.player_id: hs.score for hs in PlayerScore.query.filter_by(league_id=league.id).all()}

#         for entry in entries:
#             p1_score = historical_scores.get(entry.player1_id, 0)
#             p2_score = historical_scores.get(entry.player2_id, 0)
#             p3_score = historical_scores.get(entry.player3_id, 0)
#             total_score = p1_score + p2_score + p3_score

#             leaderboard.append({
#                 'entry': entry,
#                 'user_name': entry.user.full_name,
#                 'player1_name': f"{entry.player1.surname} {entry.player1.name} ",
#                 'player1_score': p1_score,
#                 'player2_name': f"{entry.player2.surname} {entry.player2.name}",
#                 'player2_score': p2_score,
#                 'player3_name': f"{entry.player3.surname} {entry.player3.name}",
#                 'player3_score': p3_score,
#                 'total_score': total_score
#             })

#     else:
#         # --- LOGIC FOR LIVE LEAGUES (New on-demand calculation) ---
#         print("League is active. Calculating live scores.")
#         for entry in entries:
#             score1 = entry.player1.current_score if entry.player1 and entry.player1.current_score is not None else 0
#             score2 = entry.player2.current_score if entry.player2 and entry.player2.current_score is not None else 0
#             score3 = entry.player3.current_score if entry.player3 and entry.player3.current_score is not None else 0
#             total_score = score1 + score2 + score3

#             leaderboard.append({
#                 'entry': entry,
#                 'user_name': entry.user.full_name,
#                 'player1_name': f"{entry.player1.surname} {entry.player1.name} ",
#                 'player1_score': score1,
#                 'player2_name': f"{entry.player2.surname} {entry.player2.name}",
#                 'player2_score': score2,
#                 'player3_name': f"{entry.player3.surname} {entry.player3.name}",
#                 'player3_score': score3,
#                 'total_score': total_score
#             })

#     # --- COMMON LOGIC FOR SORTING AND RANKING ---
#     # This part is the same for both live and finalized leagues
#     leaderboard.sort(key=lambda x: x['total_score'])
#     for i, item in enumerate(leaderboard):
#         item['rank'] = i + 1

#     current_user_entry = next((item for item in leaderboard if item['entry'].user_id == current_user.id), None)

#     return render_template('league/view_league.html',
#                            league=league,
#                            leaderboard=leaderboard,
#                            user_entry=current_user_entry,
#                            now=datetime.utcnow())

#club league view
@league_bp.route('/club-view/<int:league_id>')
@login_required
def club_league_view(league_id):
    """
    Renders the club admin's view of one of their created leagues.
    """
    league = League.query.get_or_404(league_id)

    # Security check: ensure the club admin owns this league
    if not isinstance(current_user, Club) or league.club_id != current_user.id:
        flash("You can only view leagues created by your club.", "danger")
        return redirect(url_for('main.club_dashboard'))

    # Use the cached leaderboard method - same as user view
    leaderboard_data = league.get_leaderboard_()

    return render_template(
        'league/club_league_view.html',
        title=f"View {league.name}",
        league=league,
        leaderboard=leaderboard_data,  # Now using cached method
        now=datetime.utcnow()
    )

# Cache invalidation for league routes
def invalidate_league_caches(league_id):
    """Invalidate league-specific caches"""
    league = League.query.get(league_id)
    if league:
        league.invalidate_cache()

        # Also invalidate user caches for all participants
        for entry in league.entries:
            invalidate_user_caches(entry.user_id)


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
    club_admin = User.query.get(league.club_id)

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

    if not winner.stripe_account_id or not club_admin.stripe_account_id:
        flash("Payout failed: The winner or club admin does not have a connected Stripe account.", "danger")
        return redirect(url_for('league.manage_league', league_id=league.id))

        winner_amount, admin_amount, error = process_league_payouts(league, winner, club_admin)

    if error:
        flash(f"An error occurred with the payout: {error}", "danger")
        return redirect(url_for('admin.edit_league', league_id=league.id))


    # Stripe payout logic would go here
    print(f"PAYOUT: Transferring €{final_prize_amount:.2f} to winner {winner.full_name}")
    # --- END OF PAYOUT CALCULATION ---

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


    # Send winner notification email to all participants
    send_winner_notification_email(league)

    flash(f'League finalized! Winner: {winner.full_name} (€{winner_amount:.2f}). Club Profit: €{admin_amount:.2f}. Payouts processed.', 'success')
    return redirect(url_for('league.manage_league', league_id=league.id))


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


@league_bp.route('/resend-winner-email/<int:league_id>', methods=['POST'])
@login_required
def resend_winner_email(league_id):
    league = League.query.get_or_404(league_id)

    # --- Unified Authorization Check ---
    is_authorized = False
    # Check if the user is a site admin
    if getattr(current_user, 'is_site_admin', False):
        is_authorized = True
    # Else, check if they are a club admin who owns this league
    elif getattr(current_user, 'is_club_admin', False) and league.club_id == current_user.id:
        is_authorized = True

    if not is_authorized:
        flash('You do not have permission to perform this action.', 'danger')
        return redirect(url_for('main.index'))
    # --- End of Authorization Check ---

    if not league.is_finalized or not league.winner:
        flash('This league has not been finalized yet.', 'warning')
        # Redirect back to the appropriate dashboard
        if getattr(current_user, 'is_site_admin', False):
            return redirect(url_for('admin.edit_league', league_id=league.id))
        else:
            return redirect(url_for('league.manage_league', league_id=league.id))

    # Use the shared utility function to send the email
    send_winner_notification_email(league)

    flash(f'Winner notification email has been resent for "{league.name}".', 'success')

    # Redirect back to the page they came from
    if getattr(current_user, 'is_site_admin', False):
        return redirect(url_for('admin.edit_league', league_id=league.id))
    else:
        return redirect(url_for('league.manage_league', league_id=league.id))