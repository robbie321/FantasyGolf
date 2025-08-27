from flask import render_template, current_app, flash, redirect, url_for, jsonify
from flask_login import login_required
from .. import cache
import requests

from . import player_bp
from ..models import Player
from .. import db

from ..data_golf_client import DataGolfClient
from ..sportradar_client import SportradarClient


# --- Player Rankings DATAGOLF Leaderboard Route ---
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


# sports radar

@player_bp.route('/all')
@login_required
def all_players():
    def get_sportradar_profiles_map():
        # --- DEBUGGING ---
        print("\n--- 1. Fetching Sportradar Player Profiles Map ---")
        client = SportradarClient()
        profiles, error = client.get_player_profiles()
        if error or not profiles:
            print(f"Error fetching player profiles: {error}")
            return {}
        return {f"{p.get('first_name', '')} {p.get('last_name', '')}": p for p in profiles}
    # --- END DEBUGGING ---

    

     # Fetch data from both sources
    local_players = Player.query.order_by(Player.surname).all()
    sportradar_profiles = get_sportradar_profiles_map()

    print(sportradar_profiles)  # For debugging

    # Merge the two data sources
    combined_player_data = []
    for player in local_players:
        # Find the corresponding Sportradar profile by matching the full name
        profile_data = sportradar_profiles.get(player.full_name())
        
        combined_player_data.append({
            'player': player,
            'profile': profile_data # This will be None if no match is found
        })


    # Sort the list of dictionaries by the 'last_name', then 'first_name'
    sorted_players = sorted(combined_player_data, key=lambda p: (p.get('last_name', ''), p.get('first_name', '')))

    return render_template('player/all_players.html', players=combined_player_data, title="All Players")



# --- Route for displaying a single player's detailed profile from Sportradar ---

@player_bp.route('/profile/<string:player_id>')
@login_required
def single_player_profile(player_id):
    """Displays a detailed profile for a single player using their Sportradar ID."""
    client = SportradarClient()
    # --- DEBUGGING ---
    print(f"\n--- 3. Player Profile Route ---")
    print(f"Received request for Sportradar player_id: {player_id}")
    # ---
    player_data, error = client.get_single_player_profile(player_id)

    if error:
        flash(f"Could not retrieve player profile from the API: {error}", "danger")
        return redirect(url_for('player.all_players'))

    # 2. Fetch the headshot manifest
    # headshot_map, error = client.get_headshot_manifest()
    # headshot_url = None
    # if error:
    #     flash("Could not retrieve player headshot manifest.", "warning")
    # elif headshot_map:
    #     # --- DEBUGGING ---
    #     print(f"--- 4. Looking up headshot for ID: {player_id} ---")
    #     image_id = headshot_map.get(player_id)
    #     print(f"Found image_id: {image_id}")
    #     # ---
    #     if image_id:
    #         # 4. Construct the final, correctly sized image URL
    #         headshot_url = f"{client.base_image_url}/{image_id}/240x240-crop.jpg"
    #         # --- DEBUGGING ---
    #         print(f"Constructed headshot URL: {headshot_url}")
    #         # ---

    print("-----------------------------------\n")

    return render_template(
        'player/sportradar_profile.html',
        player=player_data,
        # headshot_url=headshot_url
    )

@player_bp.route('/api/sportradar_profile/<string:player_id>')
@login_required
def api_sportradar_profile(player_id):
    """
    API endpoint to fetch a player's Sportradar profile data as JSON.
    """
    client = SportradarClient()
    player_data, error = client.get_single_player_profile(player_id)

    if error:
        return jsonify({'error': f'Could not retrieve player profile: {error}'}), 500

    if not player_data:
        return jsonify({'error': 'Player not found'}), 404

    # Extract only the data we need to keep the payload small
    profile = {
        'full_name': f"{player_data.get('first_name', '')} {player_data.get('last_name', '')}",
        'country': player_data.get('country'),
        'birth_date': player_data.get('birth_date'),
        'height': player_data.get('height'),
        'turned_pro': player_data.get('turned_pro'),
        'handedness': player_data.get('handedness'),
        'headshot_url': url_for('static', filename=f"/fantasy_league_app/static/images/headshots/{player_data.get('id', '')}.png")
    }
    return jsonify(profile)


@cache.memoize(timeout=3600)  # Cache this entire list for 1 hour
def get_all_sportradar_profiles():
    """
    Helper function to get all player profiles from Sportradar.
    This version is more robust and handles API errors gracefully.
    """
    print("--- FETCHING SPORT RADAR PLAYER LIST (CACHE MISS) ---") # For debugging
    client = SportradarClient()
    all_profiles, error = client.get_player_profiles()

    # If there's an error or the data is empty, return an empty list
    # This prevents the main route from failing with a 502 error.
    if error or not all_profiles:
        print(f"Error fetching from Sportradar: {error}")
        return [] # Always return a list

    return all_profiles

@player_bp.route('/api/sportradar_profile_by_name/<int:dg_id>')
@login_required
def api_sportradar_profile_by_name(dg_id):
    """
    Finds a Sportradar profile by matching the player's name from our DB.
    This version is production-ready with Redis caching.
    """
    # Step 1: Get the player's name from our local database
    player = Player.query.filter_by(dg_id=dg_id).first()
    if not player:
        return jsonify({'error': 'Player not found in local database'}), 404

    player_full_name = player.full_name()

    # Step 2: Get the list of all players from Sportradar (this will hit the cache)
    all_profiles = get_all_sportradar_profiles()
    if not all_profiles:
        return jsonify({'error': 'Could not fetch player list from Sportradar. The service may be down.'}), 502

    # Step 3: Find the matching player in the Sportradar list
    sportradar_player = next((p for p in all_profiles if p.get('first_name', '') in player_full_name and p.get('last_name', '') in player_full_name), None)

    if not sportradar_player or not sportradar_player.get('id'):
        return jsonify({'error': f'Player "{player_full_name}" not found in Sportradar player list.'}), 404

    # Step 4: Use the found ID to get the detailed profile (this can also be cached)
    sportradar_id = sportradar_player['id']

    # Use a dynamic cache key based on the player ID
    @cache.memoize(timeout=600) # Cache each individual profile for 10 minutes
    def get_detailed_profile(s_id):
        client = SportradarClient()
        return client.get_single_player_profile(s_id)

    detailed_profile, error = get_detailed_profile(sportradar_id)

    if error:
        return jsonify({'error': f'Could not retrieve detailed profile from Sportradar: {error}'}), 502

    # Step 5: Format and return the final data
    profile_data = {
        'full_name': f"{detailed_profile.get('first_name', '')} {detailed_profile.get('last_name', '')}",
        'country': detailed_profile.get('country'),
        'birth_date': detailed_profile.get('birth_date'),
        'height': detailed_profile.get('height'),
        'weight': detailed_profile.get('weight'),
        'turned_pro': detailed_profile.get('turned_pro'),
        'handedness': detailed_profile.get('handedness'),
        'headshot_url': url_for('static', filename=f"images/headshots/{dg_id}.png")
    }

    return jsonify(profile_data)
