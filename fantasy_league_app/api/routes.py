from flask import jsonify, current_app
from flask_login import login_required
from fantasy_league_app.models import Player
import requests
from . import api_bp
import re
# fantasy_league_app/api/routes.py

from flask import jsonify, current_app
from flask_login import login_required
from ..data_golf_client import DataGolfClient #
from ..models import Player
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