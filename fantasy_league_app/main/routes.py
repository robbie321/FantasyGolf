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
from fantasy_league_app.cache_utils import CacheManager, cache_result

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

    @cache_result('league_data', timeout=180)  # 3 minute cache
    def get_public_leagues_data(search_term=None):
        query = League.query.filter(
            League.is_public == True,
            League.is_finalized == False
        )

        if search_term:
            query = query.filter(League.name.ilike(f'%{search_term}%'))

        leagues = query.order_by(League.start_date).all()

        # Convert to dict for JSON serialization
        return [
            {
                'id': league.id,
                'name': league.name,
                'start_date': league.start_date.isoformat(),
                'entry_fee': league.entry_fee,
                'entry_count': len(league.entries),
                'max_entries': league.max_entries,
                'tour': league.tour
            }
            for league in leagues
        ]

    leagues_data = get_public_leagues_data(search_query)
    return render_template('main/browse_leagues.html',
                         leagues=leagues_data,
                         search_query=search_query)

@main_bp.route('/user_dashboard')
@user_required
@password_reset_required
def user_dashboard():
    now = datetime.utcnow()

    # Cache user-specific data
    @cache_result('user_data',
                  key_func=lambda: CacheManager.cache_key_for_user_leagues(current_user.id),
                  timeout=300)  # 5 minute cache
    def get_user_dashboard_data():
        user_entries = LeagueEntry.query.filter_by(user_id=current_user.id).all()

        # Enhanced Statistics Calculation
        leagues_played = len(user_entries)
        leagues_won = League.query.filter_by(winner_id=current_user.id, is_finalized=True).count()
        win_percentage = (leagues_won / leagues_played * 100) if leagues_played > 0 else 0

        stats = {
            'leagues_played': leagues_played,
            'leagues_won': leagues_won,
            'win_percentage': f"{win_percentage:.1f}%"
        }

        # Categorize Leagues with cached leaderboards
        live_leagues = []
        upcoming_leagues = []
        past_leagues = []
        leaderboard_cache = {}

        for entry in user_entries:
            league = entry.league

            # Use cached leaderboard calculation
            if league.id not in leaderboard_cache:
                leaderboard_cache[league.id] = league.get_leaderboard()

            final_leaderboard = leaderboard_cache[league.id]
            user_entry_data = next(
                (item for item in final_leaderboard if item.get('entry_id') == entry.id),
                None
            )

            if user_entry_data:
                league_data = {
                    'id': league.id,
                    'name': league.name,
                    'league_code': league.league_code,
                    'entries': len(final_leaderboard),
                    'rank': user_entry_data.get('position', 'N/A'),
                    'prizePool': league.prize_amount,
                    'entryFee': league.entry_fee,
                    'tour': league.tour
                }

                # Sort into categories
                if league.is_finalized:
                    league_data['status'] = 'Past'
                    past_leagues.append(league_data)
                elif now >= league.start_date:
                    league_data['status'] = 'Live'
                    live_leagues.append(league_data)
                else:
                    league_data['status'] = 'Upcoming'
                    upcoming_leagues.append(league_data)

        return {
            'live_leagues': live_leagues,
            'upcoming_leagues': upcoming_leagues,
            'past_leagues': past_leagues,
            'stats': stats
        }

    dashboard_data = get_user_dashboard_data()

    return render_template('main/user_dashboard.html',
                         live_leagues=dashboard_data['live_leagues'],
                         upcoming_leagues=dashboard_data['upcoming_leagues'],
                         past_leagues=dashboard_data['past_leagues'],
                         stats=dashboard_data['stats'],
                         now=now)

@main_bp.route('/club_dashboard')
@user_required
@password_reset_required
def club_dashboard():
    if not getattr(current_user, 'is_club_admin', False):
        flash('You do not have permission to access the club dashboard.', 'warning')
        return redirect(url_for('main.user_dashboard'))

    # Cache club dashboard data
    @cache_result('league_data',
                  key_func=lambda: CacheManager.make_key('club_dashboard', current_user.id),
                  timeout=300)  # 5 minute cache
    def get_club_dashboard_data():
        leagues = League.query.filter_by(club_id=current_user.id).order_by(League.start_date.desc()).all()

        # Calculate revenue and stats
        club_revenue = 0.0
        total_participants = 0
        for league in leagues:
            num_entries = len(league.entries)
            club_revenue += max(0, league.entry_fee - 2.50)  # Account for fees
            total_participants += num_entries

        now = datetime.utcnow()
        active_leagues_count = sum(1 for league in leagues if not league.is_finalized and league.end_date > now)
        total_entries_count = sum(len(league.entries) for league in leagues)

        return {
            'leagues': [league.to_dict() for league in leagues],
            'club_revenue': club_revenue,
            'total_participants': total_participants,
            'active_leagues_count': active_leagues_count,
            'total_entries_count': total_entries_count,
            'club_data': current_user.to_dict()
        }

    dashboard_data = get_club_dashboard_data()

    return render_template(
        'main/club_dashboard.html',
        club=current_user,
        club_leagues=dashboard_data['leagues'],
        club_revenue=dashboard_data['club_revenue'],
        club_data_for_js=dashboard_data['club_data'],
        club_leagues_for_js=dashboard_data['leagues'],
        active_leagues_count=dashboard_data['active_leagues_count'],
        total_entries_count=dashboard_data['total_entries_count'],
        now=datetime.utcnow()
    )



# --- NEW: Route for User Profiles ---
@main_bp.route('/profile/<int:user_id>')
@user_required
def view_profile(user_id):
    user = User.query.get_or_404(user_id)

    # Cache user profile data
    @cache_result('user_data',
                  key_func=lambda: CacheManager.make_key('profile', user_id),
                  timeout=600)  # 10 minute cache
    def get_user_profile_data():
        entries = LeagueEntry.query.filter_by(user_id=user.id).all()

        leagues_played = len(entries)
        leagues_won = League.query.filter_by(winner_id=user.id, is_finalized=True).count()
        total_winnings = user.total_winnings or 0.0
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
            winnings = 0.0

            if league.is_finalized:
                leaderboard = league.get_leaderboard()  # This is cached
                user_entry = next(
                    (item for item in leaderboard if item.get('entry_id') == entry.id),
                    None
                )
                if user_entry:
                    rank = user_entry.get('position', 'N/A')

                if league.winner_id == user.id:
                    winnings = league.entry_fee * len(league.entries)

            league_history.append({
                'league_name': league.name,
                'league_id': league.id,
                'rank': rank,
                'is_winner': league.winner_id == user.id,
                'winnings': f"€{winnings:.2f}"
            })

        return {
            'stats': stats,
            'league_history': league_history
        }

    profile_data = get_user_profile_data()

    return render_template('main/profile.html',
                         user=user,
                         stats=profile_data['stats'],
                         league_history=profile_data['league_history'])

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

@main_bp.route('/health/cache')
def cache_health():
    """Cache health check endpoint"""
    try:
        # Test cache write/read
        test_key = CacheManager.make_key('health_check', datetime.utcnow().timestamp())
        test_value = {'status': 'ok', 'timestamp': datetime.utcnow().isoformat()}

        cache.set(test_key, test_value, timeout=60)
        retrieved = cache.get(test_key)

        if retrieved == test_value:
            cache.delete(test_key)  # Clean up
            return jsonify({'cache_status': 'healthy', 'redis_connection': 'ok'}), 200
        else:
            return jsonify({'cache_status': 'unhealthy', 'error': 'write/read mismatch'}), 500

    except Exception as e:
        return jsonify({'cache_status': 'unhealthy', 'error': str(e)}), 500

# Cache invalidation helper for main routes
def invalidate_user_caches(user_id):
    """Invalidate user-specific caches"""
    cache.delete(CacheManager.cache_key_for_user_leagues(user_id))
    cache.delete(CacheManager.make_key('profile', user_id))
    cache.delete(CacheManager.make_key('club_dashboard', user_id))