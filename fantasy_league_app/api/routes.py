from flask import jsonify, current_app
from flask_login import login_required
from fantasy_league_app.models import Player
import requests
from . import api_bp
# fantasy_league_app/api/routes.py

from flask import jsonify, current_app
from flask_login import login_required
from ..data_golf_client import DataGolfClient # <-- ADD THIS IMPORT
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