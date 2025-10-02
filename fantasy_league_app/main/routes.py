# --- File: fantasy_league_app/main/routes.py (UPDATED - Fix NameError: db is not defined) ---
from flask import render_template, url_for, redirect, flash, current_app, request, send_from_directory
from flask_login import login_required, current_user
from fantasy_league_app.models import League, LeagueEntry, User, Club
from . import main_bp
from fantasy_league_app import db, stripe_client
from fantasy_league_app.utils import password_reset_required
from sqlalchemy import func, distinct, desc
from datetime import datetime, timedelta
import requests
from ..data_golf_client import DataGolfClient
from ..models import User, League, LeagueEntry, PlayerScore
from ..auth.decorators import user_required
import stripe
from fantasy_league_app.cache_utils import CacheManager, cache_result
from flask import send_from_directory
import os

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

@main_bp.route('/service-worker.js')
def service_worker():
    """Serve service worker from root for proper scope"""

    response = send_from_directory(
        os.path.join(app.root_path, 'static'),
        'service-worker.js',
        mimetype='application/javascript'
    )

    # Add headers to prevent caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Service-Worker-Allowed'] = '/'

    return response

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
        # leagues_played = len(user_entries)
        # leagues_won = League.query.filter_by(winner_id=current_user.id, is_finalized=True).count()
        # win_percentage = (leagues_won / leagues_played * 100) if leagues_played > 0 else 0

        # stats = {
        #     'leagues_played': leagues_played,
        #     'leagues_won': leagues_won,
        #     'win_percentage': f"{win_percentage:.1f}%"
        # }

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
            # 'stats': stats
        }

    dashboard_data = get_user_dashboard_data()


    profile_stats = calculate_user_stats(current_user.id)
    league_history = get_enhanced_league_history(current_user.id)
    recent_activity = get_recent_activity(current_user.id)

    return render_template('main/user_dashboard.html',
                         live_leagues=dashboard_data['live_leagues'],
                         upcoming_leagues=dashboard_data['upcoming_leagues'],
                         past_leagues=dashboard_data['past_leagues'],
                         stats=profile_stats,
                         now=now,
                         user=current_user,
                         league_history=league_history,
                         recent_activity=recent_activity,
                         is_own_profile=True)

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

@main_bp.route('/profile')
@user_required
def my_profile():
    """Route for viewing own profile"""
    return redirect(url_for('main.view_profile', user_id=current_user.id))

# --- NEW: Route for User Profiles ---
@main_bp.route('/profile/<int:user_id>')
@user_required
def view_profile(user_id):
    # Get the target user
    target_user = User.query.get_or_404(user_id)
    is_own_profile = current_user.id == user_id

    # Calculate comprehensive statistics
    stats = calculate_user_stats(target_user.id)

    # Get league history with enhanced data
    league_history = get_enhanced_league_history(target_user.id)

    # Get recent activity
    recent_activity = get_recent_activity(target_user.id)

    return render_template('main/profile.html',
                         user=target_user,
                         stats=stats,
                         league_history=league_history,
                         recent_activity=recent_activity,
                         is_own_profile=is_own_profile,
                         current_user=current_user)


def calculate_user_stats(user_id):
    """Calculate comprehensive user statistics"""
    from ..models import LeagueEntry, League

    # Get all user's league entries
    entries = LeagueEntry.query.filter_by(user_id=user_id).all()

    # Basic counts
    leagues_played = len(entries)
    leagues_won = len([e for e in entries if e.league.winner_id == user_id])

    # Calculate win percentage
    win_percentage = round((leagues_won / leagues_played * 100), 1) if leagues_played > 0 else 0

    # Calculate total winnings (you'll need to add this logic based on your prize structure)
    total_winnings = calculate_total_winnings(user_id)

    # Calculate current streak (consecutive wins)
    current_streak = calculate_current_streak(user_id)

    # Calculate days active (days since first league)
    days_active = calculate_days_active(user_id)

    # Calculate user level based on activities
    user_level = calculate_user_level(leagues_played, leagues_won, total_winnings)

    return {
        'leagues_played': leagues_played,
        'leagues_won': leagues_won,
        'win_percentage': win_percentage,
        'total_winnings': total_winnings,
        'current_streak': current_streak,
        'days_active': days_active,
        'user_level': user_level,
        'average_rank': calculate_average_rank(entries),
        'best_rank': calculate_best_rank(entries),
        'leagues_this_month': calculate_leagues_this_month(user_id)
    }


def calculate_total_winnings(user_id):
    """Calculate total prize money won by user"""
    from ..models import League

    # Get all leagues won by this user
    won_leagues = League.query.filter_by(winner_id=user_id, is_finalized=True).all()

    total = 0
    for league in won_leagues:
        # Calculate prize based on your business logic
        # This is a simplified version - adjust based on your prize structure
        if league.entries:
            total_pot = len(league.entries) * league.entry_fee
            # Assuming winner gets 80% of pot (adjust based on your model)
            prize = total_pot * 0.8
            total += prize

    return round(total, 2)

def calculate_current_streak(user_id):
    """Calculate current consecutive wins streak"""
    from ..models import League, LeagueEntry

    # Get user's recent finalized leagues ordered by date
    recent_leagues = db.session.query(League).join(LeagueEntry).filter(
        LeagueEntry.user_id == user_id,
        League.is_finalized == True
    ).order_by(desc(League.end_date)).limit(20).all()

    streak = 0
    for league in recent_leagues:
        if league.winner_id == user_id:
            streak += 1
        else:
            break  # Streak broken

    return streak

def calculate_days_active(user_id):
    """Calculate days since user first joined a league"""
    from ..models import LeagueEntry

    first_entry = LeagueEntry.query.filter_by(user_id=user_id).order_by(LeagueEntry.id).first()
    if not first_entry:
        return 0

    # Assuming you have a created_at field on LeagueEntry
    # If not, you can use the league's start_date
    first_date = getattr(first_entry, 'created_at', first_entry.league.start_date)
    days_active = (datetime.utcnow() - first_date).days
    return max(0, days_active)

def calculate_user_level(leagues_played, leagues_won, total_winnings):
    """Calculate user level based on activity and performance"""

    # Simple leveling system - adjust as needed
    points = 0
    points += leagues_played * 10  # 10 points per league
    points += leagues_won * 50     # 50 bonus points per win
    points += int(total_winnings)  # 1 point per euro won

    # Level thresholds
    if points < 50:
        return 1
    elif points < 150:
        return 2
    elif points < 300:
        return 3
    elif points < 500:
        return 4
    elif points < 750:
        return 5
    else:
        return min(10, 5 + (points - 750) // 200)  # Cap at level 10

def calculate_average_rank(entries):
    """Calculate user's average finishing position"""
    if not entries:
        return 0

    total_rank = 0
    finalized_count = 0

    for entry in entries:
        if entry.league.is_finalized:
            # You'll need to implement rank calculation logic
            # This is a placeholder - adjust based on how you store ranks
            rank = calculate_entry_rank(entry)
            if rank:
                total_rank += rank
                finalized_count += 1

    return round(total_rank / finalized_count, 1) if finalized_count > 0 else 0

def calculate_best_rank(entries):
    """Find user's best (lowest) finishing position"""
    best = float('inf')

    for entry in entries:
        if entry.league.is_finalized:
            rank = calculate_entry_rank(entry)
            if rank and rank < best:
                best = rank

    return best if best != float('inf') else 0

def calculate_entry_rank(entry):
    """Calculate the rank of a specific entry in its league"""
    # Get all entries in the same league
    all_entries = entry.league.entries

    # Sort by total score (assuming lower score is better)
    sorted_entries = sorted(all_entries, key=lambda e: e.total_score or float('inf'))

    # Find the rank (1-indexed)
    for rank, e in enumerate(sorted_entries, 1):
        if e.id == entry.id:
            return rank

    return None

def calculate_leagues_this_month(user_id):
    """Count leagues played this month"""
    from ..models import LeagueEntry, League

    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    count = db.session.query(LeagueEntry).join(League).filter(
        LeagueEntry.user_id == user_id,
        League.start_date >= start_of_month
    ).count()

    return count

def get_enhanced_league_history(user_id, limit=20):
    """Get detailed league history for the user"""
    from ..models import LeagueEntry, League

    entries = db.session.query(LeagueEntry).join(League).filter(
        LeagueEntry.user_id == user_id
    ).order_by(desc(League.end_date)).limit(limit).all()

    history = []
    for entry in entries:
        league = entry.league

        # Calculate rank in this league
        rank = calculate_entry_rank(entry)

        # Calculate winnings for this league
        winnings = 0
        if league.winner_id == user_id and league.is_finalized:
            total_pot = len(league.entries) * league.entry_fee
            winnings = total_pot * 0.8  # Adjust based on your prize structure

        # Count total players
        total_players = len(league.entries)

        history.append({
            'league_id': league.id,
            'league_name': league.name,
            'rank': rank,
            'total_players': total_players,
            'winnings': round(winnings, 2),
            'is_winner': league.winner_id == user_id,
            'date_finished': league.end_date.strftime('%Y-%m-%d') if league.is_finalized else None,
            'is_active': not league.is_finalized
        })

    return history

def get_recent_activity(user_id, limit=10):
    """Get recent user activity for the activity feed"""
    from ..models import LeagueEntry, League

    activities = []

    # Get recent league joins
    recent_entries = db.session.query(LeagueEntry).join(League).filter(
        LeagueEntry.user_id == user_id
    ).order_by(desc(LeagueEntry.id)).limit(limit).all()

    for entry in recent_entries:
        league = entry.league

        # League join activity
        activities.append({
            'type': 'league_join',
            'description': f"Joined '{league.name}'",
            'time_ago': get_time_ago(getattr(entry, 'created_at', league.start_date)),
            'icon': 'plus-circle'
        })

        # League win activity (if won and finalized)
        if league.winner_id == user_id and league.is_finalized:
            activities.append({
                'type': 'league_win',
                'description': f"Won '{league.name}'!",
                'time_ago': get_time_ago(league.end_date),
                'icon': 'trophy'
            })

    # Sort by most recent and limit
    activities.sort(key=lambda x: x['time_ago'], reverse=True)
    return activities[:limit]

def get_time_ago(date_time):
    """Convert datetime to human-readable time ago string"""
    if not date_time:
        return "Unknown"

    now = datetime.utcnow()
    diff = now - date_time

    if diff.days > 30:
        return f"{diff.days // 30} month{'s' if diff.days // 30 != 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "Just now"

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