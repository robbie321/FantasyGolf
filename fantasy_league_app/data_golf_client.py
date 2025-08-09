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

    def get_live_player_stats(self, tour='pga'):
        """
        Fetches detailed live tournament stats for all players, including all
        strokes gained categories, distance, and accuracy.
        """
        endpoint = f"preds/live-tournament-stats?stats=sg_putt,sg_app,sg_ott,sg_total,distance,accuracy,total&display=value&tour={tour}"
        data, error = self._make_request(endpoint)
        if error:
            return None, error
        return data, None

    def get_live_tournament_stats(self, tour='pga'):
        """Fetches live tournament stats for a given tour."""
        endpoint = f"preds/live-tournament-stats?tour={tour}&stats=sg_total,total&display=value"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data.get('live_stats', []), None

    def get_betting_odds(self, tour='pga'):
        """Fetches outright win odds for a given tour."""
        endpoint = f"betting-tools/outrights?tour={tour}&market=win&odds_format=decimal&file_format=json"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data.get('odds', []), None

    def get_tournament_schedule(self, tour='pga'):
        """Fetches the upcoming tournament schedule for a tour."""
        endpoint = f"get-schedule?tour={tour}&file_format=json"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data.get('schedule', []), None

    def get_tournament_field_updates(self, event_id, tour='pga'):
        """Fetches the player field for a specific tournament."""
        endpoint = f"field-updates?tour={tour}&event_id={event_id}"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data.get('field', []), None