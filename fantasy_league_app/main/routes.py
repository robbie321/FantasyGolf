# --- File: fantasy_league_app/main/routes.py (UPDATED - Fix NameError: db is not defined) ---
from flask import render_template, url_for, redirect, flash, current_app, request
from flask_login import login_required, current_user
from fantasy_league_app.models import League, LeagueEntry, User
from . import main_bp
from fantasy_league_app import db, stripe_client
from fantasy_league_app.utils import password_reset_required
from sqlalchemy import func, distinct
from datetime import datetime, timedelta
import requests
from ..data_golf_client import DataGolfClient
from ..models import User, League, LeagueEntry, PlayerScore

@main_bp.route('/offline.html')
def offline():
    return render_template('offline.html')

@main_bp.route('/')
def index():
# --- Calculate Homepage Stats ---
    active_players = db.session.query(func.count(distinct(LeagueEntry.user_id))).scalar()
    live_leagues = League.query.filter(League.is_finalized == False).count()
    total_prizes = db.session.query(func.sum(League.prize_amount)).filter(League.payout_status == 'paid').scalar() or 0

    # Calculate this week's prize pool
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    this_week_prize_pool = db.session.query(func.sum(League.entry_fee * db.session.query(func.count(LeagueEntry.id)).filter(LeagueEntry.league_id == League.id).as_scalar())) \
        .filter(League.start_date >= start_of_week, League.start_date <= end_of_week).scalar() or 0

    stats = {
        'active_players': active_players,
        'live_leagues': live_leagues,
        'total_prizes': f"€{total_prizes:,.2f}",
        'this_week_prize_pool': f"€{this_week_prize_pool:,.2f}"
    }
    # --- END of Stats Calculation ---

    client = DataGolfClient()
    top_players, error = client.get_player_rankings()
    if error:
        flash(f"Could not load world rankings: {error}", "warning")
        top_players = [] # Ensure top_players is a list even on error

    top_players = top_players[:10]

    top_leagues = League.query.filter_by(is_public=True)\
        .outerjoin(League.entries)\
        .group_by(League.id)\
        .order_by(func.count(LeagueEntry.id).desc())\
        .limit(10).all()

    return render_template('main/index.html', stats=stats, top_players=top_players, top_leagues=top_leagues)


# --- Route for Browsing Public Leagues ---
@main_bp.route('/browse-leagues')
@login_required
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
@login_required
@password_reset_required
def user_dashboard():
    user_entries = LeagueEntry.query.filter_by(user_id=current_user.id).all()

    leagues_data = []
    # Use a cache to avoid re-calculating the same leaderboard multiple times
    leaderboard_cache = {}

    for entry in user_entries:
        league = entry.league

        # Check if we have already calculated the leaderboard for this league
        if league.id not in leaderboard_cache:
            all_league_entries = LeagueEntry.query.filter_by(league_id=league.id).all()
            leaderboard = []

            if league.is_finalized:
                # --- LOGIC FOR FINALIZED LEAGUES ---
                historical_scores = {hs.player_id: hs.score for hs in PlayerScore.query.filter_by(league_id=league.id).all()}
                for e in all_league_entries:
                    p1_score = historical_scores.get(e.player1_id, 0)
                    p2_score = historical_scores.get(e.player2_id, 0)
                    p3_score = historical_scores.get(e.player3_id, 0)
                    total_score = p1_score + p2_score + p3_score
                    leaderboard.append({'entry_id': e.id, 'total_score': total_score})
            else:
                # --- LOGIC FOR LIVE LEAGUES ---
                for e in all_league_entries:
                    s1 = e.player1.current_score if e.player1 and e.player1.current_score is not None else 0
                    s2 = e.player2.current_score if e.player2 and e.player2.current_score is not None else 0
                    s3 = e.player3.current_score if e.player3 and e.player3.current_score is not None else 0
                    total_score = s1 + s2 + s3
                    leaderboard.append({'entry_id': e.id, 'total_score': total_score})

            # Sort and rank
            leaderboard.sort(key=lambda x: x['total_score'])
            for i, item in enumerate(leaderboard):
                item['rank'] = i + 1

            # Cache the result
            leaderboard_cache[league.id] = leaderboard

        # Find the current user's entry in the calculated leaderboard
        final_leaderboard = leaderboard_cache[league.id]
        user_entry_data = next((item for item in final_leaderboard if item['entry_id'] == entry.id), None)

        if user_entry_data:
            leagues_data.append({
                'league_name': league.name,
                'league_id': league.id,
                'total_score': user_entry_data['total_score'],
                'current_rank': user_entry_data['rank'], # Use the calculated rank
                'total_entries': len(final_leaderboard),
                'prize_pool': f"€{league.prize_amount}",
                'start_date': league.start_date
            })

    return render_template('main/user_dashboard.html', leagues_data=leagues_data, today=datetime.utcnow())

@main_bp.route('/club_dashboard')
@login_required
@password_reset_required
def club_dashboard():
    if not getattr(current_user, 'is_club_admin', False):
        flash('You do not have permission to access the club dashboard.', 'warning')
        return redirect(url_for('main.user_dashboard'))

    # Fetch leagues created by this club
    # current_user is a Club object here, so current_user.id is the club_id
    created_leagues = League.query.filter_by(club_id=current_user.id).all()

    club = current_user
    club_revenue = 0

    # ---  Calculate Club Revenue ---
    # Get a list of all league IDs created by the current club
    total_revenue = 0
    total_prizes_paid = 0

    if league_ids := [league.id for league in created_leagues]:
        # Calculate the total revenue from all entries in this club's leagues
        total_revenue_generated = db.session.query(func.sum(League.entry_fee)) \
            .select_from(LeagueEntry).join(League) \
            .filter(League.id.in_(league_ids)).scalar() or 0

        # Calculate the total prize money for leagues that have been paid out
        total_prizes_paid = db.session.query(func.sum(League.prize_amount)) \
            .filter(League.id.in_(league_ids), League.payout_status == 'paid').scalar() or 0

        # The club's final revenue is their share of the total pot minus the prizes they've paid
        club_revenue = (total_revenue_generated * 0.70) - total_prizes_paid
    # --- END revenue logic ---

    # I might categorize these later (Upcoming, Live, Completed)
    # For now, just list them.
    club_leagues = []
    for league in created_leagues:
        club_leagues.append({
            'name': league.name,
            'code': league.league_code,
            'entry_fee': league.entry_fee,
            'id': league.id
            # Add more details as needed, e.g., number of entries, status
        })

    return render_template('main/club_dashboard.html', club=club, club_leagues=club_leagues, club_revenue=club_revenue)



# --- NEW: Route for User Profiles ---
@main_bp.route('/profile/<int:user_id>')
@login_required
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
@login_required
def onboard_stripe():
    """
    Handles the request to create or update a user's Stripe account.
    """
    try:
        # Step 1: Create a Stripe account if the user doesn't have one
        if not current_user.stripe_account_id:
            account = stripe_client.create_express_account(current_user.email)
            if account:
                current_user.stripe_account_id = account.id
                db.session.commit()
            else:
                flash('Could not create a Stripe account. Please try again later.', 'danger')
                return redirect(url_for('main.user_dashboard'))

        # Step 2: Create the account link to redirect the user
        account_link = stripe_client.create_account_link(
            account_id=current_user.stripe_account_id,
            refresh_url=url_for('main.user_dashboard', _external=True) + '#stripe-section',
            return_url=url_for('main.user_dashboard', _external=True) + '#stripe-section'
        )

        if account_link:
            return redirect(account_link.url)
        else:
            flash('Could not connect to Stripe at this time. Please try again.', 'danger')
            return redirect(url_for('main.user_dashboard'))

    except Exception as e:
        current_app.logger.error(f"Stripe onboarding error for user {current_user.id}: {e}")
        flash('An unexpected error occurred. Please contact support.', 'danger')
        return redirect(url_for('main.user_dashboard'))

@main_bp.route('/stripe/connect/return')
@login_required
def stripe_connect_return():
    """Handle the user's return from the Stripe onboarding process."""
    flash("Payout account setup is complete!", "success")
    if getattr(current_user, 'is_club_admin', False):
        return redirect(url_for('main.club_dashboard'))
    return redirect(url_for('main.user_dashboard'))

@main_bp.route('/stripe/connect/refresh')
@login_required
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