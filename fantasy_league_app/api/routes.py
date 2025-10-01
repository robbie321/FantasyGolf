from flask import jsonify, current_app
from flask_login import login_required
from fantasy_league_app.models import Player
import requests
import json
from .. import db
import re
# fantasy_league_app/api/routes.py
from pywebpush import webpush, WebPushException
from flask_login import login_required
from ..data_golf_client import DataGolfClient #
from ..models import Player, PushSubscription, PlayerBucket
from . import api_bp
from datetime import datetime, timezone
from fantasy_league_app.cache_utils import CacheManager, cache_result
from fantasy_league_app import cache

@api_bp.route('/player-stats/<int:dg_id>')
@login_required
def get_player_stats(dg_id):
    """
    API endpoint to fetch live tournament stats for a specific player
    using the DataGolfClient.
    """
    # This check is good for ensuring the player exists in your DB, but it is not strictly
    # necessary for the API call itself if you remove it.
    # Player.query.filter_by(dg_id=dg_id).first_or_404()

    client = DataGolfClient()
    data, error = client.get_live_player_stats() # Use the new client method

    if error:
        return jsonify({'error': f'Could not connect to the data provider: {error}'}), 500

    if 'live_stats' not in data:
        return jsonify({'error': 'No live stats available at the moment.'}), 404

    player_stats = None
    for p_stat in data['live_stats']:
        if p_stat.get('dg_id') and int(p_stat.get('dg_id')) == dg_id:
            player_stats = p_stat
            break

    if player_stats:
        # The 'total' key is now requested directly by the client
        return jsonify(player_stats)
    else:
        return jsonify({'error': f'Live stats not found for this player.'}), 404

@api_bp.route('/tee-times/<string:tour>')
@login_required
def get_tee_times(tour):
    """
    API endpoint to fetch tee times for a specific tour's current tournament.
    Returns organized tee time data with player information.
    """
    @cache_result('api_data',
                  key_func=lambda tour: CacheManager.make_key('tee_times', tour),
                  timeout=900)  # 15 minute cache
    def fetch_tee_times_data(tour):
        client = DataGolfClient()
        field_data, error = client.get_tee_times(tour)

        if error or not field_data:
            return {'error': 'Could not retrieve tee times data'}

        # Get current round
        current_round = field_data.get('current_round', 1)
        event_name = field_data.get('event_name', 'Current Tournament')

        # Organize players by tee time
        tee_time_key = f'r{current_round}_teetime'
        tee_times = {}

        for player in field_data.get('field', []):
            tee_time_str = player.get(tee_time_key)

            if tee_time_str:
                # Parse tee time
                try:
                    tee_time_dt = datetime.strptime(tee_time_str, '%Y-%m-%d %H:%M')
                    time_key = tee_time_dt.strftime('%H:%M')

                    if time_key not in tee_times:
                        tee_times[time_key] = {
                            'time': time_key,
                            'datetime': tee_time_dt.isoformat(),
                            'players': []
                        }

                    # Get player info from your database
                    dg_id = player.get('dg_id')
                    db_player = Player.query.filter_by(dg_id=dg_id).first()

                    player_info = {
                        'dg_id': dg_id,
                        'name': player.get('player_name', 'Unknown'),
                        'country': player.get('country', ''),
                        'current_score': player.get('current_score'),
                        'current_pos': player.get('current_pos', '-'),
                        'odds': db_player.odds if db_player else None,
                        'status': player.get('status', 'active')
                    }

                    tee_times[time_key]['players'].append(player_info)

                except (ValueError, TypeError) as e:
                    continue

        # Sort tee times chronologically
        sorted_tee_times = sorted(tee_times.values(), key=lambda x: x['time'])

        return {
            'event_name': event_name,
            'tour': tour.upper(),
            'current_round': current_round,
            'tee_times': sorted_tee_times,
            'total_groups': len(sorted_tee_times)
        }

    result = fetch_tee_times_data(tour)

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    return jsonify(result)


# --- Live Leaderboard API Endpoint ---
@api_bp.route('/live-leaderboard/<string:tour>')
@login_required
def get_live_leaderboard(tour):
    """
    Fetches the live in-play leaderboard from the DataGolf API.
    """

    @cache_result('api_data',
                  key_func=lambda tour: CacheManager.make_key('live_leaderboard', tour),
                  timeout=180)  # 3 minute cache for live data
    def fetch_live_leaderboard_data(tour):
        api_key = current_app.config.get('DATA_GOLF_API_KEY')
        if not api_key:
            return {'error': 'API key not configured'}

        url = f"https://feeds.datagolf.com/preds/in-play?tour={tour}&dead_heat=no&odds_format=percent&key={api_key}"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if 'data' in data:
                def get_sort_key(player):
                    pos = player.get('current_pos', '999')
                    numbers = re.findall(r'\d+', pos)
                    return int(numbers[0]) if numbers else 999

                sorted_data = sorted(data['data'], key=get_sort_key)
                return sorted_data
            else:
                return []

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Failed to fetch live leaderboard for tour '{tour}': {e}")
            return {'error': 'Failed to fetch data from external API'}
        except Exception as e:
            current_app.logger.error(f"An unexpected error occurred: {e}")
            return {'error': 'An internal server error occurred'}

    result = fetch_live_leaderboard_data(tour)

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 503 if 'Failed to fetch' in result['error'] else 500

    return jsonify(result)

@api_bp.route('/tour-schedule/<string:tour>')
@login_required
def get_tournament_schedules(tour):
    """
    API endpoint to fetch the upcoming tournament schedule for a tour.
    """
    @cache_result('api_data',
                  key_func=lambda tour: CacheManager.make_key('tournament_schedule', tour),
                  timeout=3600)  # 1 hour cache for schedule data
    def fetch_tournament_schedule(tour):
        client = DataGolfClient()
        schedule, error = client.get_tournament_schedule(tour)

        if error:
            return {'error': str(error)}

        return schedule

    result = fetch_tournament_schedule(tour)

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    return jsonify(result)
    # client = DataGolfClient()
    # schedule, error = client.get_tournament_schedule(tour)

    # if error:
    #     return jsonify({"error": str(error)}), 500

    # return jsonify(schedule)

@api_bp.route('/tournament-details/<int:bucket_id>')
@login_required
def get_tournament_details(bucket_id):
    """
    Fetches tournament start date and first tee time for a given player bucket.
    """
    @cache_result('static_data',
                  key_func=lambda bucket_id: CacheManager.make_key('tournament_details', bucket_id),
                  timeout=1800)  # 30 minute cache
    def fetch_tournament_details(bucket_id):
        bucket = PlayerBucket.query.get(bucket_id)
        if not bucket or not bucket.tour:
            return {'error': 'Player bucket has no associated tour.'}

        client = DataGolfClient()
        field_data, error = client.get_tournament_field_updates(bucket.tour)

        if error or not field_data or 'field' not in field_data:
            return {'error': 'Could not retrieve tournament data.'}

        event_name = field_data.get('event_name', 'N/A')
        earliest_tee_time = None

        for player in field_data.get('field', []):
            tee_time_str = player.get('r1_teetime')
            if tee_time_str:
                try:
                    tee_time = datetime.strptime(tee_time_str, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
                    if earliest_tee_time is None or tee_time < earliest_tee_time:
                        earliest_tee_time = tee_time
                except (ValueError, TypeError):
                    continue

        start_date_str = earliest_tee_time.strftime('%d %b %Y') if earliest_tee_time else "TBC"
        formatted_tee_time = earliest_tee_time.strftime('%I:%M %p %Z') if earliest_tee_time else "TBC"

        return {
            'event_name': event_name,
            'start_date': start_date_str,
            'tee_time': formatted_tee_time
        }

    result = fetch_tournament_details(bucket_id)

    if 'error' in result:
        return jsonify(result), 404 if 'not found' in result['error'].lower() else 500

    return jsonify(result)

@api_bp.route('/player-analytics/<int:dg_id>')
@login_required
def get_player_analytics(dg_id):
    """
    Comprehensive analytics for a specific player.
    Returns skill ratings, recent form, course history, and predictions.
    Accepts optional 'tour' query parameter (defaults to 'pga').
    """
    from flask import request

    # Get tour from query parameter, default to 'pga'
    tour = request.args.get('tour', 'pga').lower()

    # Validate tour parameter
    if tour not in ['pga', 'euro', 'kft', 'alt']:
        tour = 'pga'

    @cache_result('api_data',
                  key_func=lambda dg_id, tour: CacheManager.make_key('player_analytics', dg_id, tour),
                  timeout=3600)  # 1 hour cache
    def fetch_player_analytics(dg_id, tour):  # ADD tour parameter here
        client = DataGolfClient()

        # Get player from database
        player = Player.query.filter_by(dg_id=dg_id).first()
        if not player:
            return {'error': 'Player not found'}

        analytics = {
            'player': {
                'name': player.full_name(),
                'dg_id': player.dg_id,
                'odds': player.odds,
                'current_score': player.current_score
            },
            'skill_ratings': {},
            'recent_form': [],
            'course_fit': {},
            'predictions': {}
        }

        # Fetch skill ratings (not tour-specific)
        try:
            skill_data, skill_error = client.get_player_skill_ratings()
            if not skill_error and skill_data and isinstance(skill_data, list):
                player_skill = next((p for p in skill_data if p.get('dg_id') == dg_id), None)
                if player_skill:
                    analytics['skill_ratings'] = {
                        'overall': player_skill.get('sg_total'),
                        'driving': player_skill.get('sg_ott'),  # Strokes Gained: Off the Tee
                        'approach': player_skill.get('sg_app'),  # Strokes Gained: Approach
                        'short_game': player_skill.get('sg_arg'),  # Strokes Gained: Around the Green
                        'putting': player_skill.get('sg_putt')
                    }
        except Exception as e:
            current_app.logger.warning(f"Could not fetch skill ratings: {e}")

        # Fetch baseline history fit (tour-specific)
        try:
            fantasy_data, fantasy_error = client.get_fantasy_projections(tour, site='draftkings')
            if not fantasy_error and fantasy_data and isinstance(fantasy_data, list):
                player_fantasy = next((p for p in fantasy_data if p.get('dg_id') == dg_id), None)
                if player_fantasy:
                    analytics['fantasy_projections'] = {
                        'proj_points_total': player_fantasy.get('proj_points_total'),
                        'proj_points_finish': player_fantasy.get('proj_points_finish'),
                        'proj_points_scoring': player_fantasy.get('proj_points_scoring'),
                        'proj_ownership': player_fantasy.get('proj_ownership'),
                        'salary': player_fantasy.get('salary'),
                        'value': player_fantasy.get('value'),
                        'r1_teetime': player_fantasy.get('r1_teetime')
                    }
        except Exception as e:
            current_app.logger.warning(f"Could not fetch fantasy projections for tour {tour}: {e}")

        # Fetch pre-tournament predictions (tour-specific)
        try:
            pred_data, pred_error = client.get_pre_tournament_predictions(tour)

            if not pred_error and pred_data:
                # Ensure pred_data is a list
                if isinstance(pred_data, dict) and 'baseline' in pred_data:
                    pred_data = pred_data['baseline']
                elif isinstance(pred_data, dict) and 'data' in pred_data:
                    pred_data = pred_data['data']

                if isinstance(pred_data, list):
                    player_pred = next((p for p in pred_data if p.get('dg_id') == dg_id), None)
                    if player_pred:
                        # Convert decimal odds to probability percentage
                        # Probability = (1 / decimal_odds) * 100
                        analytics['predictions'] = {
                            'win_prob': (1 / player_pred.get('win', 999)) * 100 if player_pred.get('win') else 0,
                            'top5_prob': (1 / player_pred.get('top_5', 999)) * 100 if player_pred.get('top_5') else 0,
                            'top10_prob': (1 / player_pred.get('top_10', 999)) * 100 if player_pred.get('top_10') else 0,
                            'top20_prob': (1 / player_pred.get('top_20', 999)) * 100 if player_pred.get('top_20') else 0,
                            'make_cut_prob': (1 / player_pred.get('make_cut', 999)) * 100 if player_pred.get('make_cut') else 0
                        }
        except Exception as e:
            current_app.logger.warning(f"Could not fetch predictions for tour {tour}: {e}")

        return analytics

    result = fetch_player_analytics(dg_id, tour)  # PASS tour here

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 404

    return jsonify(result)


@api_bp.route('/player-form/<int:dg_id>')
@login_required
def get_player_form(dg_id):
    """
    Get recent tournament form for a player (last 10 events).
    """
    @cache_result('api_data',
                  key_func=lambda dg_id: CacheManager.make_key('player_form', dg_id),
                  timeout=1800)  # 30 minute cache
    def fetch_player_form(dg_id):
        client = DataGolfClient()

        player = Player.query.filter_by(dg_id=dg_id).first()
        if not player:
            return {'error': 'Player not found'}

        form_data, error = client.get_player_recent_form(dg_id)
        if error or not form_data:
            return {'error': 'Could not retrieve form data'}

        # Process and return last 10 events
        recent_events = form_data[:10] if isinstance(form_data, list) else []

        return {
            'player_name': player.full_name(),
            'recent_form': recent_events
        }

    result = fetch_player_form(dg_id)

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 404

    return jsonify(result)


@api_bp.route('/leaderboard-insights/<string:tour>')
@login_required
def get_leaderboard_insights(tour):
    """
    Enhanced leaderboard with skill ratings and probabilities.
    """
    @cache_result('api_data',
                  key_func=lambda tour: CacheManager.make_key('leaderboard_insights', tour),
                  timeout=300)  # 5 minute cache
    def fetch_leaderboard_insights(tour):
        client = DataGolfClient()

        # Get live leaderboard
        leaderboard_data, lb_error = client.get_in_play_stats(tour)
        if lb_error or not leaderboard_data:
            return {'error': 'Could not retrieve leaderboard'}

        # Get predictions
        pred_data, pred_error = client.get_pre_tournament_predictions(tour)
        pred_map = {}
        if not pred_error and pred_data:
            pred_map = {p.get('dg_id'): p for p in pred_data}

        # Enhance leaderboard with insights
        enhanced_leaderboard = []
        for player in leaderboard_data[:50]:  # Top 50 players
            dg_id = player.get('dg_id')
            predictions = pred_map.get(dg_id, {})

            enhanced_player = {
                **player,
                'win_prob': round(predictions.get('win_prob', 0) * 100, 2),
                'top5_prob': round(predictions.get('top_5_prob', 0) * 100, 2),
                'top10_prob': round(predictions.get('top_10_prob', 0) * 100, 2)
            }
            enhanced_leaderboard.append(enhanced_player)

        return enhanced_leaderboard

    result = fetch_leaderboard_insights(tour)

    if isinstance(result, dict) and 'error' in result:
        return jsonify(result), 500

    return jsonify(result)


@api_bp.route('/vapid_public_key', methods=['GET'])
def vapid_public_key():
    """Provides the VAPID public key to the frontend."""
    public_key = current_app.config.get('VAPID_PUBLIC_KEY')
    private_key = current_app.config.get('VAPID_PRIVATE_KEY')

    print(f"DEBUG: Public key from config: {public_key}")
    print(f"DEBUG: Private key from config: {private_key[:20]}...")  # Only first 20 chars for security
    print(f"DEBUG: Private key length: {len(private_key) if private_key else 0}")

    # Check if the key is missing or is still the default placeholder
    if not public_key or 'YOUR_GENERATED_PUBLIC_KEY' in public_key:
        print("!!! LOG ERROR: VAPID_PUBLIC_KEY is not configured on the server.")
        return jsonify({'error': 'VAPID public key not configured on the server.'}), 500

    print(f"LOG: Sending VAPID public key to client: {public_key[:10]}...")
    return jsonify({'public_key': public_key})

@api_bp.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    """Saves a user's push notification subscription to the database."""
    print(f"LOG: Received a new subscription request for user {current_user.id}")
    subscription_data = request.get_json()
    if not subscription_data:
        print("LOG ERROR: No subscription data received in request.")
        return jsonify({'error': 'No subscription data provided'}), 400

    endpoint = subscription_data.get('endpoint')

    # Check if this exact subscription already exists for this user
    subscription = PushSubscription.query.filter_by(user_id=current_user.id, endpoint=endpoint).first()

    if subscription:
        print(f"LOG: Subscription for endpoint {endpoint} already exists for user {current_user.id}.")
    else:
        print(f"LOG: Creating new subscription for user {current_user.id}.")
        new_subscription = PushSubscription(
            user_id=current_user.id,
            subscription_json=json.dumps(subscription_data)
        )
        db.session.add(new_subscription)
        db.session.commit()
        print(f"LOG: Successfully saved new subscription for user {current_user.id}.")

    return jsonify({'success': True}), 201

# Example of a route to trigger a push notification
# In your real app, this logic would be in a background task
@api_bp.route('/send_notification/<int:user_id>', methods=['POST'])
@login_required
def send_notification(user_id):
    if not current_user.is_site_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    user_subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    if not user_subscriptions:
        return jsonify({'error': 'User has no subscriptions'}), 404

    message = json.dumps({
        "title": "Fantasy Fairways",
        "body": "Your league is about to start! Check your picks.",
        "icon": "/static/images/icons/icon-192x192.png"
    })

    for sub in user_subscriptions:
        try:
            webpush(
                subscription_info=json.loads(sub.subscription_json),
                data=message,
                vapid_private_key=current_app.config['VAPID_PRIVATE_KEY'],
                vapid_claims={"sub": current_app.config['VAPID_CLAIM_EMAIL']}
            )
        except WebPushException as ex:
            print(f"WebPushException: {ex}")
            # If the subscription is expired or invalid, delete it
            if ex.response and ex.response.status_code in [404, 410]:
                db.session.delete(sub)
                db.session.commit()

    return jsonify({'success': True, 'sent_to': len(user_subscriptions)})