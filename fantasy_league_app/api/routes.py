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

    # api_key = current_app.config.get('DATA_GOLF_API_KEY')
    # if not api_key:
    #     return jsonify({'error': 'API key not configured'}), 500

    # url = f"https://feeds.datagolf.com/preds/in-play?tour={tour}&dead_heat=no&odds_format=percent&key={api_key}"

    # try:
    #     response = requests.get(url)
    #     response.raise_for_status()  # Raise an exception for bad status codes
    #     data = response.json()

    #     # Check for the 'data' key in the response
    #     if 'data' in data:
    #         def get_sort_key(player):
    #             """Helper function to extract a number from the position string."""
    #             pos = player.get('current_pos', '999')
    #             # Find all numbers in the string (e.g., 'T21' -> '21')
    #             numbers = re.findall(r'\d+', pos)
    #             if numbers:
    #                 return int(numbers[0])
    #             # Return a large number for non-standard positions like 'CUT' or 'WD'
    #             return 999

    #         sorted_data = sorted(data['data'], key=get_sort_key)
    #         return jsonify(sorted_data)
    #     else:
    #         # Handle cases where the API returns a valid response but no data
    #         # (e.g., tournament not live)
    #         return jsonify([])

    # except requests.exceptions.RequestException as e:
    #     current_app.logger.error(f"Failed to fetch live leaderboard for tour '{tour}': {e}")
    #     return jsonify({'error': 'Failed to fetch data from external API'}), 503
    # except Exception as e:
    #     current_app.logger.error(f"An unexpected error occurred: {e}")
    #     return jsonify({'error': 'An internal server error occurred'}), 500

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
    # bucket = PlayerBucket.query.get_or_404(bucket_id)
    # if not bucket.tour:
    #     return jsonify({'error': 'Player bucket has no associated tour.'}), 404

    # client = DataGolfClient()
    # field_data, error = client.get_tournament_field_updates(bucket.tour)

    # if error or not field_data or 'field' not in field_data:
    #     return jsonify({'error': 'Could not retrieve tournament data.'}), 500

    # event_name = field_data.get('event_name', 'N/A')
    # earliest_tee_time = None

    # # Iterate through the 'field' list to find the earliest r1_teetime
    # for player in field_data.get('field', []):
    #     tee_time_str = player.get('r1_teetime')
    #     if tee_time_str:
    #         try:
    #             tee_time = datetime.strptime(tee_time_str, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
    #             if earliest_tee_time is None or tee_time < earliest_tee_time:
    #                 earliest_tee_time = tee_time
    #         except (ValueError, TypeError):
    #             continue

    # # Format the data for the frontend
    # start_date_str = earliest_tee_time.strftime('%d %b %Y') if earliest_tee_time else "TBC"
    # formatted_tee_time = earliest_tee_time.strftime('%I:%M %p %Z') if earliest_tee_time else "TBC"

    # return jsonify({
    #     'event_name': event_name,
    #     'start_date': start_date_str,
    #     'tee_time': formatted_tee_time
    # })

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