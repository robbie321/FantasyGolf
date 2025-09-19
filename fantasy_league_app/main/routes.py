# --- File: fantasy_league_app/main/routes.py (UPDATED - Fix NameError: db is not defined) ---
from flask import render_template, url_for, redirect, flash, current_app, request, send_from_directory
from flask_login import login_required, current_user
from fantasy_league_app.models import League, LeagueEntry, User, Club
from . import main_bp
from fantasy_league_app import db, stripe_client
from fantasy_league_app.utils import password_reset_required
from sqlalchemy import func, distinct
from datetime import datetime, timedelta
import requests
from ..data_golf_client import DataGolfClient
from ..models import User, League, LeagueEntry, PlayerScore
from ..auth.decorators import user_required
import stripe

@main_bp.route('/offline.html')
def offline():
    return render_template('offline.html')

@main_bp.route('/terms')
def terms_and_conditions():
    """Renders the terms and conditions page."""
    return render_template('main/terms_and_conditions.html', title="Terms & Conditions")

@main_bp.route('/privacy')
def privacy_policy():
    """Renders the privacy policy page."""
    return render_template('main/privacy_policy.html', title="Privacy Policy")


@main_bp.route('/')
@main_bp.route('/index')
def index():
    """
    Renders the landing page for logged-out users, or redirects
    logged-in users to their appropriate dashboard.
    """
    # If the user is logged in, send them to their dashboard
    if current_user.is_authenticated:
        if current_user.is_club_admin:
            return redirect(url_for('main.club_dashboard'))
        else:
            return redirect(url_for('main.user_dashboard'))

    # Otherwise, show the main landing page
    return render_template('main/index.html', title="Welcome")



@main_bp.route('/clubs')
def clubs_landing():
    """Route for the clubs landing page."""
    return render_template('main/clubs_landing.html', title="For Golf Clubs")

# --- Route for Browsing Public Leagues ---
@main_bp.route('/browse-leagues')
@user_required
def browse_leagues():
    search_query = request.args.get('search', '')

    # Base query for public leagues that are not past their entry deadline
    query = League.query.filter(
        League.is_public == True,
        League.is_finalized == False
    )

    if search_query:
        query = query.filter(League.name.ilike(f'%{search_query}%'))

    leagues = query.order_by(League.start_date).all()

    return render_template('main/browse_leagues.html', leagues=leagues, search_query=search_query)

# @main_bp.route('/user_dashboard')
# @login_required
# @password_reset_required
# def user_dashboard():
#     if getattr(current_user, 'is_club_admin', False):
#         flash('You do not have permission to access the user dashboard.', 'warning')
#         return redirect(url_for('main.club_dashboard'))

#     # Fetch leagues the user has joined
#     my_entries = LeagueEntry.query.filter_by(user_id=current_user.id).options(db.joinedload(LeagueEntry.league)).all()

#     user_leagues = []
#     for entry in my_entries:
#         if entry.league:
#             user_leagues.append({
#                 'entry_id': entry.id,
#                 'start_date': entry.league.start_date,
#                 'league_obj': entry.league,
#                 'entry_name': entry.entry_name,
#                 'league_name': entry.league.name,
#                 'league_code': entry.league.league_code,
#                 'total_odds': entry.total_odds,
#                 'league_id': entry.league.id,
#                 'current_rank': entry.current_rank
#             })

#     return render_template('main/user_dashboard.html', user_leagues=user_leagues, today=datetime.utcnow())

@main_bp.route('/user_dashboard')
@user_required
@password_reset_required
def user_dashboard():
    now = datetime.utcnow()
    user_entries = LeagueEntry.query.filter_by(user_id=current_user.id).all()

     # --- Enhanced Statistics Calculation ---
    leagues_played = len(user_entries)
    leagues_won = League.query.filter_by(winner_id=current_user.id, is_finalized=True).count()
    # total_winnings = user.total_winnings or 0.0

    # Calculate win percentage
    win_percentage = (leagues_won / leagues_played * 100) if leagues_played > 0 else 0

    stats = {
        'leagues_played': leagues_played,
        'leagues_won': leagues_won,
        'win_percentage': f"{win_percentage:.1f}%"
    }

    # --- Categorize Leagues ---
    live_leagues = []
    upcoming_leagues = []
    past_leagues = []
    leaderboard_cache = {}

    for entry in user_entries:
        league = entry.league

        # --- On-the-fly rank and score calculation (reused for all categories) ---
        if league.id not in leaderboard_cache:
            all_league_entries = LeagueEntry.query.filter_by(league_id=league.id).all()
            leaderboard = []
            if league.is_finalized:
                historical_scores = {hs.player_id: hs.score for hs in PlayerScore.query.filter_by(league_id=league.id).all()}
                for e in all_league_entries:
                    s1 = historical_scores.get(e.player1_id, 0)
                    s2 = historical_scores.get(e.player2_id, 0)
                    s3 = historical_scores.get(e.player3_id, 0)
                    leaderboard.append({'entry_id': e.id, 'total_score': s1+s2+s3})
            else: # Live leagues
                for e in all_league_entries:
                    s1 = e.player1.current_score if e.player1 and e.player1.current_score is not None else 0
                    s2 = e.player2.current_score if e.player2 and e.player2.current_score is not None else 0
                    s3 = e.player3.current_score if e.player3 and e.player3.current_score is not None else 0
                    leaderboard.append({'entry_id': e.id, 'total_score': s1+s2+s3})

            leaderboard.sort(key=lambda x: x['total_score'])
            for i, item in enumerate(leaderboard):
                item['rank'] = i + 1
            leaderboard_cache[league.id] = leaderboard

        final_leaderboard = leaderboard_cache[league.id]
        user_entry_data = next((item for item in final_leaderboard if item['entry_id'] == entry.id), None)

        if user_entry_data:
            # 1. Convert the base league object into a dictionary
            league_data = league.to_dict()
            # 2. Update the dictionary with your user-specific and calculated data
            league_data.update({
                'rank': user_entry_data['rank'],
                'entries': len(final_leaderboard)
            })
            # league_data = {
            #     'league': league,
            #     'total_score': user_entry_data['total_score'],
            #     'current_rank': user_entry_data['rank'],
            #     'total_entries': len(final_leaderboard)
            # }

            # --- Sort into categories ---
            if league.is_finalized:
                league_data['status'] = 'Past'
                past_leagues.append(league_data)
            elif now >= league.start_date:
                league_data['status'] = 'Live'
                live_leagues.append(league_data)
            else:
                league_data['status'] = 'Upcoming'
                upcoming_leagues.append(league_data)

    return render_template('main/user_dashboard.html',
                           live_leagues=live_leagues,
                           upcoming_leagues=upcoming_leagues,
                           past_leagues=past_leagues,
                           stats=stats,
                           now=datetime.utcnow())

# def user_dashboard():
#     user_entries = LeagueEntry.query.filter_by(user_id=current_user.id).all()

#     leagues_data = []
#     # Use a cache to avoid re-calculating the same leaderboard multiple times
#     leaderboard_cache = {}

#     for entry in user_entries:
#         league = entry.league

#         # Check if we have already calculated the leaderboard for this league
#         if league.id not in leaderboard_cache:
#             all_league_entries = LeagueEntry.query.filter_by(league_id=league.id).all()
#             leaderboard = []

#             if league.is_finalized:
#                 # --- LOGIC FOR FINALIZED LEAGUES ---
#                 historical_scores = {hs.player_id: hs.score for hs in PlayerScore.query.filter_by(league_id=league.id).all()}
#                 for e in all_league_entries:
#                     p1_score = historical_scores.get(e.player1_id, 0)
#                     p2_score = historical_scores.get(e.player2_id, 0)
#                     p3_score = historical_scores.get(e.player3_id, 0)
#                     total_score = p1_score + p2_score + p3_score
#                     leaderboard.append({'entry_id': e.id, 'total_score': total_score})
#             else:
#                 # --- LOGIC FOR LIVE LEAGUES ---
#                 for e in all_league_entries:
#                     s1 = e.player1.current_score if e.player1 and e.player1.current_score is not None else 0
#                     s2 = e.player2.current_score if e.player2 and e.player2.current_score is not None else 0
#                     s3 = e.player3.current_score if e.player3 and e.player3.current_score is not None else 0
#                     total_score = s1 + s2 + s3
#                     leaderboard.append({'entry_id': e.id, 'total_score': total_score})

#             # Sort and rank
#             leaderboard.sort(key=lambda x: x['total_score'])
#             for i, item in enumerate(leaderboard):
#                 item['rank'] = i + 1

#             # Cache the result
#             leaderboard_cache[league.id] = leaderboard

#         # Find the current user's entry in the calculated leaderboard
#         final_leaderboard = leaderboard_cache[league.id]
#         user_entry_data = next((item for item in final_leaderboard if item['entry_id'] == entry.id), None)

#         if user_entry_data:
#             leagues_data.append({
#                 'league_name': league.name,
#                 'league_id': league.id,
#                 'total_score': user_entry_data['total_score'],
#                 'current_rank': user_entry_data['rank'], # Use the calculated rank
#                 'total_entries': len(final_leaderboard),
#                 'prize_pool': f"€{league.prize_amount}",
#                 'start_date': league.start_date
#             })

#     return render_template('main/user_dashboard.html', leagues_data=leagues_data, today=datetime.utcnow())

@main_bp.route('/club_dashboard')
@user_required
@password_reset_required
def club_dashboard():
    if not getattr(current_user, 'is_club_admin', False):
        flash('You do not have permission to access the club dashboard.', 'warning')
        return redirect(url_for('main.user_dashboard'))

    club = current_user

    # 1. Get the original League OBJECTS from the database
    leagues = League.query.filter_by(club_id=club.id).order_by(League.start_date.desc()).all()

    # 2. Calculate revenue using the list of OBJECTS
    club_revenue = 0.0
    total_participants = 0
    for league in leagues:
        num_entries = len(league.entries)
        club_revenue += league.entry_fee - 2.50
        total_participants += num_entries

    now = datetime.utcnow()
    # Calculate the number of active leagues
    active_leagues_count = sum(1 for league in leagues if not league.is_finalized and league.end_date > now)

    # Calculate the total number of entries across all leagues
    total_entries_count = sum(len(league.entries) for league in leagues)

    # 3. Prepare JSON-safe data for the JavaScript section using the OBJECTS
    club_data_for_js = club.to_dict()
    club_leagues_for_js = [league.to_dict() for league in leagues]

    # 4. Pass everything to the template
    return render_template(
        'main/club_dashboard.html',
        club=club,
        club_leagues=leagues,      # Pass the list of OBJECTS to the main template
        club_revenue=club_revenue,
        club_data_for_js=club_data_for_js,
        club_leagues_for_js=club_leagues_for_js, # Pass the list of DICTIONARIES to the script block
        active_leagues_count=active_leagues_count,
        total_entries_count=total_entries_count,
        now=now
    )



# --- NEW: Route for User Profiles ---
@main_bp.route('/profile/<int:user_id>')
@user_required
def view_profile(user_id):
    user = User.query.get_or_404(user_id)

    # Fetch all entries for this user
    entries = LeagueEntry.query.filter_by(user_id=user.id).all()

     # --- Enhanced Statistics Calculation ---
    leagues_played = len(entries)
    leagues_won = League.query.filter_by(winner_id=user.id, is_finalized=True).count()
    total_winnings = user.total_winnings or 0.0

    # Calculate win percentage
    win_percentage = (leagues_won / leagues_played * 100) if leagues_played > 0 else 0

    stats = {
        'leagues_played': leagues_played,
        'leagues_won': leagues_won,
        'win_percentage': f"{win_percentage:.1f}%",
        'total_winnings': f"€{total_winnings:.2f}"
    }

    # Prepare league history data
    league_history = []
    for entry in entries:
        league = entry.league
        rank = "N/A"
        winnings = 0.0 # Placeholder for winnings

        if league.is_finalized:
            # Sort entries by final score to determine rank
            sorted_entries = sorted(league.entries, key=lambda e: (e.player1.current_score + e.player2.current_score + e.player3.current_score))
            try:
                # Find the index of the current entry in the sorted list
                rank = [i for i, item in enumerate(sorted_entries) if item.id == entry.id][0] + 1
            except IndexError:
                rank = "N/A"

            # If the user is the winner, you could assign winnings here
            # For now, we are just showing if they won
            if league.winner_id == user.id:
                 # This is a simple example. You might have more complex prize logic
                 # For now, let's assume the winner takes the whole pot.
                 winnings = league.entry_fee * len(league.entries)


        league_history.append({
            'league_name': league.name,
            'league_id': league.id,
            'rank': rank,
            'is_winner': league.winner_id == user.id,
            'winnings': f"€{winnings:.2f}"
        })

    return render_template('main/profile.html', user=user, stats=stats, league_history=league_history)


# --- Stripe Connect Onboarding Routes ---

@main_bp.route('/onboard-stripe', methods=['POST'])
@user_required
def onboard_stripe():
    """
    Handles the request to create or update a user's Stripe account.
    """
    if not isinstance(current_user, Club):
        flash("Only clubs can connect a Stripe account.", "danger")
        return redirect(url_for('main.user_dashboard'))

    club = current_user
    try:
        # Set the API key from your app's configuration
        stripe.api_key = current_app.config['STRIPE_SECRET_KEY']

        # This is for debugging - it will print the key to your console.
        # Remove this line after you confirm it's working.
        print(f"DEBUG: Using Stripe Secret Key: {stripe.api_key}")
    except KeyError:
        flash("Stripe API keys are not configured on the server.", "danger")
        return redirect(url_for('main.club_dashboard'))

    if not club.stripe_account_id:
        # Create a new Stripe account for the club if one doesn't exist
        try:
            account = stripe.Account.create(
                type='express',
                country='IE',  # Or your country code
                email=club.email,
                capabilities={
                    'card_payments': {'requested': True},
                    'transfers': {'requested': True},
                },
            )
            club.stripe_account_id = account.id
            db.session.commit()
        except Exception as e:
            flash(f"Could not create Stripe account: {e}", "danger")
            return redirect(url_for('main.club_dashboard'))

    # Create an account link for onboarding
    try:
        account_link = stripe.AccountLink.create(
            account=club.stripe_account_id,
            refresh_url=url_for('main.club_dashboard', _external=True),
            return_url=url_for('main.club_dashboard', _external=True),

            # --- ADD THIS REQUIRED PARAMETER ---
            type='account_onboarding',

        )
        return redirect(account_link.url)
    except Exception as e:
        # This is the block that is currently being triggered
        flash(f"Stripe Error: {e}", "danger")
        print(f"Stripe AccountLink Error: {e}")
        return redirect(url_for('main.club_dashboard'))
    # try:
    #     # Step 1: Create a Stripe account if the user doesn't have one
    #     if not current_user.stripe_account_id:
    #         account = stripe_client.create_express_account(current_user.email)
    #         if account:
    #             current_user.stripe_account_id = account.id
    #             db.session.commit()
    #         else:
    #             flash('Could not create a Stripe account. Please try again later.', 'danger')
    #             return redirect(url_for('main.club_dashboard'))

    #     # Step 2: Create the account link to redirect the user
    #     account_link = stripe_client.create_account_link(
    #         account_id=current_user.stripe_account_id,
    #         refresh_url=url_for('main.club_dashboard', _external=True) + '#stripe-section',
    #         return_url=url_for('main.club_dashboard', _external=True) + '#stripe-section'
    #     )

    #     if account_link:
    #         return redirect(account_link.url)
    #     else:
    #         flash('Could not connect to Stripe at this time. Please try again.', 'danger')
    #         return redirect(url_for('main.club_dashboard'))

    # except Exception as e:
    #     current_app.logger.error(f"Stripe onboarding error for user {current_user.id}: {e}")
    #     flash('An unexpected error occurred. Please contact support.', 'danger')
    #     return redirect(url_for('main.club_dashboard'))

@main_bp.route('/stripe/connect/return')
@user_required
def stripe_connect_return():
    """Handle the user's return from the Stripe onboarding process."""
    flash("Payout account setup is complete!", "success")
    if getattr(current_user, 'is_club_admin', False):
        return redirect(url_for('main.club_dashboard'))
    return redirect(url_for('main.user_dashboard'))

@main_bp.route('/stripe/connect/refresh')
@user_required
def stripe_connect_refresh():
    """Handle cases where the Stripe Account Link expires."""
    if not current_user.stripe_account_id:
        # If there's no account ID, they can't refresh. Send them to start over.
        return redirect(url_for('main.stripe_connect_onboard'))

    try:
        # Create a new Account Link for the existing account
        account_link = stripe.AccountLink.create(
            account=current_user.stripe_account_id,
            refresh_url=url_for('main.stripe_connect_refresh', _external=True),
            return_url=url_for('main.stripe_connect_return', _external=True),
            type='account_onboarding',
        )
        return redirect(account_link.url, code=303)
    except Exception as e:
        flash(f"Could not refresh connection link: {str(e)}", 'danger')
        if getattr(current_user, 'is_club_admin', False):
            return redirect(url_for('main.club_dashboard'))
        return redirect(url_for('main.user_dashboard'))

@main_bp.route('/service-worker.js')
def service_worker():
    """Serves the service worker file with the correct MIME type."""
    return send_from_directory(current_app.static_folder, 'service-worker.js', mimetype='application/javascript')