from flask import jsonify, current_app
from flask_login import login_required
from fantasy_league_app.models import Player
import requests
import json
from .. import db
import re
# fantasy_league_app/api/routes.py
from pywebpush import webpush, WebPushException
from flask import jsonify, current_app
from flask_login import login_required
from ..data_golf_client import DataGolfClient #
from ..models import Player, PushSubscription
from . import api_bp

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


# --- NEW: Live Leaderboard API Endpoint ---
@api_bp.route('/live-leaderboard/<string:tour>')
def get_live_leaderboard(tour):
    """
    Fetches the live in-play leaderboard from the DataGolf API.
    """

    api_key = current_app.config.get('DATA_GOLF_API_KEY')
    if not api_key:
        return jsonify({'error': 'API key not configured'}), 500

    url = f"https://feeds.datagolf.com/preds/in-play?tour={tour}&dead_heat=no&odds_format=percent&key={api_key}"

    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()

        # Check for the 'data' key in the response
        if 'data' in data:
            def get_sort_key(player):
                """Helper function to extract a number from the position string."""
                pos = player.get('current_pos', '999')
                # Find all numbers in the string (e.g., 'T21' -> '21')
                numbers = re.findall(r'\d+', pos)
                if numbers:
                    return int(numbers[0])
                # Return a large number for non-standard positions like 'CUT' or 'WD'
                return 999

            sorted_data = sorted(data['data'], key=get_sort_key)
            return jsonify(sorted_data)
        else:
            # Handle cases where the API returns a valid response but no data
            # (e.g., tournament not live)
            return jsonify([])

    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Failed to fetch live leaderboard for tour '{tour}': {e}")
        return jsonify({'error': 'Failed to fetch data from external API'}), 503
    except Exception as e:
        current_app.logger.error(f"An unexpected error occurred: {e}")
        return jsonify({'error': 'An internal server error occurred'}), 500


@api_bp.route('/vapid_public_key', methods=['GET'])
def vapid_public_key():
    """Provides the VAPID public key to the frontend."""
    public_key = current_app.config.get('VAPID_PUBLIC_KEY')

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