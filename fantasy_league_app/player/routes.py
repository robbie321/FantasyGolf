from flask import render_template, current_app, flash, redirect, url_for
from flask_login import login_required
import requests

from . import player_bp
from ..models import Player
from .. import db

from ..data_golf_client import DataGolfClient


# --- Player Rankings Leaderboard Route ---
@player_bp.route('/rankings')
@login_required
def rankings():
    """
    Displays a leaderboard of all players, ordered by their Data Golf rank.
    """
    client = DataGolfClient()
    all_players, error = client.get_player_rankings()
    if error:
        flash(f"Error fetching player rankings from the API: {error}", "danger")
    return render_template('player/rankings.html', players=all_players)

@player_bp.route('/profile/<int:dg_id>')
@login_required
def player_profile(dg_id):
    """
    Displays a detailed profile page for a specific player, including
    their stats fetched from the Data Golf API.
    """
    player = Player.query.filter_by(dg_id=dg_id).first()

    client = DataGolfClient()
    all_players_data, error = client.get_player_rankings()

    player_stats = {}

    if error:
        flash(f"Error fetching player stats: {error}", "danger")
    else:
        for p_data in all_players_data:
            if p_data.get('dg_id') == dg_id:
                player_stats = p_data
                break

        # If the player was not found in our local database
        if player is None:
            if player_stats:
                # Player exists in API but not in our DB, so create them
                player_name = player_stats.get('player_name', 'Unknown')
                # Split the name into first and last names
                name_parts = player_name.split(', ')
                surname, name = (name_parts[0], name_parts[1]) if len(name_parts) == 2 else (player_name, '')

                player = Player(
                    dg_id=dg_id,
                    name=name,
                    surname=surname,
                    # Odds are not in this endpoint, so they default to 0
                    # They will be updated when an admin refreshes a bucket
                )
                db.session.add(player)
                db.session.commit()
                # flash(f'{player.full_name()} has been added to the database.', 'success')
            else:
                # If the player is not in the API either, then it's a true 404
                return "Player not found", 404

        if not player_stats:
            flash(f"Could not find detailed stats for {player.full_name()} at this time.", "warning")


    return render_template('player/profile.html', player=player, stats=player_stats)