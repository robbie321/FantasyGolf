import requests
from flask import current_app

class DataGolfClient:
    """A client for interacting with the Data Golf API."""

    def __init__(self):
        self.api_key = current_app.config['DATA_GOLF_API_KEY']
        self.base_url = "https://feeds.datagolf.com"


    def _make_request(self, endpoint):
        """Helper function to make a request and handle common errors."""
        url = f"{self.base_url}/{endpoint}&key={self.api_key}"
        try:
            response = requests.get(url)
            response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
            return response.json(), None
        except requests.exceptions.RequestException as e:
            print(f"API Request Error for endpoint '{endpoint}': {e}")
            return None, str(e)

    def get_player_rankings(self):
        """Fetches the main player rankings list."""
        data, error = self._make_request("preds/get-dg-rankings?file_format=json")
        if error:
            return [], error
        return data.get('rankings', []), None

    # def get_live_player_stats(self, tour='pga'):
    #     """
    #     Fetches detailed live tournament stats for all players, including all
    #     strokes gained categories, distance, and accuracy.
    #     """
    #     endpoint = f"preds/live-tournament-stats?stats=sg_putt,sg_app,sg_ott,sg_total,distance,accuracy,total&display=value&tour={tour}"
    #     data, error = self._make_request(endpoint)
    #     if error:
    #         return None, error
    #     return data, None

    def get_in_play_stats(self, tour):
        """
        Fetches live in-play prediction stats for a given tour.
        """
        endpoint = f"{self.base_url}/preds/in-play"
        params = {
            'tour': tour,
            'dead_heat': 'no',
            'odds_format': 'percent',
            'key': self.api_key
        }
        try:
            response = requests.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            # The player data is nested inside the 'data' key
            return data.get('data', []), None
        except requests.exceptions.RequestException as e:
            return None, str(e)

    def get_live_tournament_stats(self, tour):
        """Fetches live tournament stats for a given tour."""
        endpoint = f"preds/live-tournament-stats?stats=sg_putt,sg_app,sg_ott,sg_total,distance,accuracy,total&display=value&tour={tour}"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data.get('live_stats', []), None


    # --- Method to get a specific player's round score ---
    def get_round_score(self, tour, event_id, player_dg_id):
        """
        Fetches the score for a specific player in a specific round of a tournament.
        """
        url = f"https://feeds.datagolf.com/preds/live-tournament-stats?tour={tour}&stats=round_score&round=2&display=value&key={self.api_key}"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # The API returns a list of players; we need to find the one we're looking for
            for player_data in data.get('players', []):
                if player_data.get('dg_id') == player_dg_id:
                    return player_data.get('round_score'), None

            return None, "Player not found in tournament stats."
        except requests.exceptions.RequestException as e:
            return None, str(e)

    def get_betting_odds(self, tour):
        """Fetches outright win odds for a given tour."""
        endpoint = f"betting-tools/outrights?tour={tour}&market=win&odds_format=decimal&file_format=json"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data.get('odds', []), None

    def get_tournament_schedule(self, tour):
        """Fetches the upcoming tournament schedule for a tour."""
        endpoint = f"get-schedule?tour={tour}&file_format=json"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data.get('schedule', []), None

    def get_tournament_field_updates(self, tour):
        """Fetches the player field for a specific tournament."""
        endpoint = f"field-updates?tour={tour}"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data, None


    def get_player_profiles(self):
        """
        Fetches the 2025 PGA player profiles from the Sportradar API.
        Note: This uses a different API and key.
        """
        # Get the dedicated API key for Sportradar
        sportradar_key = current_app.config.get('SPORTRADAR_API_KEY')
        if not sportradar_key:
            return None, "Sportradar API key is not configured."

        url = "https://api.sportradar.com/golf/trial/pga/v3/en/2025/players/profiles.json"
        headers = {
            "accept": "application/json",
            "x-api-key": sportradar_key
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status() # Raises an error for bad responses
            # Assuming the player data is in a 'players' key in the JSON
            return response.json().get('players', []), None
        except requests.exceptions.RequestException as e:
            print(f"Sportradar API Request Error: {e}")
            return None, str(e)

    # --- NEW METHOD FOR SPORDRADAR SINGLE PLAYER PROFILE ---
    def get_player_profile(self, player_id):
        """
        Fetches a single player's detailed profile and history from the Sportradar API.
        """
        sportradar_key = current_app.config.get('SPORTRADAR_API_KEY')
        if not sportradar_key:
            return None, "Sportradar API key is not configured."

        # The endpoint uses the player_id from Sportradar
        url = f"https://api.sportradar.com/golf/trial/pga/v3/en/2025/players/{player_id}/profile.json"
        headers = {
            "accept": "application/json",
            "x-api-key": sportradar_key
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            # The API returns the full player profile object directly
            return response.json(), None
        except requests.exceptions.RequestException as e:
            print(f"Sportradar API Request Error for player {player_id}: {e}")
            return None, str(e)

     # --- NEW METHOD FOR SPORTRADAR SINGLE PLAYER PROFILE ---
    def get_sportradar_profile(self, player_id):
        """
        Fetches a single player's detailed profile and history from the Sportradar API.
        """
        sportradar_key = current_app.config.get('SPORTRADAR_API_KEY')
        if not sportradar_key:
            return None, "Sportradar API key is not configured."

        url = f"https://api.sportradar.com/golf/trial/pga/v3/en/2025/players/{player_id}/profile.json"
        headers = {
            "accept": "application/json",
            "x-api-key": sportradar_key
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json(), None
        except requests.exceptions.RequestException as e:
            print(f"Sportradar API Request Error for player {player_id}: {e}")
            return None, str(e)