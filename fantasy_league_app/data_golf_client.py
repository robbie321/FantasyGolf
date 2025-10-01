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

    def get_tee_times(self, tour):
        """
        Fetches tee times for the current tournament on the specified tour.
        Returns player field data including tee times.
        """
        endpoint = f"field-updates?tour={tour}&file_format=json"
        data, error = self._make_request(endpoint)
        if error:
            return None, error
        return data, None

    def get_tournament_field_updates(self, tour):
        """Fetches the player field for a specific tournament."""
        endpoint = f"field-updates?tour={tour}"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data, None


    def get_player_skill_ratings(self):
        """
        Fetches skill ratings and decompositions for all players.
        Includes overall skill, driving, approach, short game, putting.
        """
        endpoint = "preds/skill-ratings?display=rank&file_format=json"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data.get('players', []), None

    def get_player_skill_decompositions(self):
        """
        Fetches detailed skill decompositions (sg_ott, sg_app, sg_arg, sg_putt).
        """
        endpoint = "preds/skill-decompositions?file_format=json"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data.get('rankings', []), None

    def get_player_course_history(self, event_id):
        """
        Fetches historical performance at a specific course/event.
        """
        endpoint = f"historical-raw-data/event-results?event_id={event_id}&file_format=json"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data, None

    def get_fantasy_projections(self, tour='pga', site='draftkings'):
        """
        Fetches fantasy projections for the current tournament.
        """
        endpoint = f"preds/fantasy-projection-defaults?tour={tour}&site={site}&slate=main&file_format=json"
        data, error = self._make_request(endpoint)
        if error:
            return [], error

        # Extract the projections list from the response
        if isinstance(data, dict):
            return data.get('projections', []), None
        elif isinstance(data, list):
            return data, None

        return [], None

    def get_player_recent_form(self, player_id=None):
        """
        Fetches recent tournament results and form.
        """
        endpoint = "historical-raw-data/player-results?file_format=json"
        if player_id:
            endpoint += f"&player_id={player_id}"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data, None

    def get_pre_tournament_predictions(self, tour='pga'):
        """
        Fetches pre-tournament predictions including finish probabilities.
        """
        endpoint = f"preds/pre-tournament?tour={tour}&odds_format=decimal&dead_heat=no&file_format=json"
        data, error = self._make_request(endpoint)
        if error:
            return [], error

        # Extract the baseline list from the response
        if isinstance(data, dict):
            return data.get('baseline', []), None
        elif isinstance(data, list):
            return data, None

        return [], None