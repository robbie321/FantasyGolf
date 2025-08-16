import requests
import xml.etree.ElementTree as ET
from flask import current_app

class SportradarClient:
    """A client for interacting with the Sportradar Golf API."""

    def __init__(self):
        self.api_key = current_app.config.get('SPORTRADAR_API_KEY')
        # CORRECTED: The base URL should not contain the year.
        self.base_url = "https://api.sportradar.com/golf/trial"
        self.base_image_url = "https://sr-cdn.sportradar.com/images/pga/players"

    def _make_request(self, endpoint):
        """Helper function to make a request and handle common errors."""
        if not self.api_key:
            return None, "Sportradar API key is not configured."

        url = f"{self.base_url}/{endpoint}"
        headers = {
            "accept": "application/json",
            "x-api-key": self.api_key
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json(), None
        except requests.exceptions.RequestException as e:
            print(f"Sportradar API Request Error for endpoint '{endpoint}': {e}")
            return None, str(e)

    def get_player_profiles(self, year="2025"):
        """Fetches all player profiles for a given season."""
        # CORRECTED: The year is now part of the endpoint string.
        endpoint = f"pga/v3/en/{year}/players/profiles.json"
        data, error = self._make_request(endpoint)
        if error:
            return [], error
        return data.get('players', []), None

    def get_single_player_profile(self, player_id):
        """Fetches a single player's detailed profile and history."""
        # CORRECTED: The year is now part of the endpoint string.
        endpoint = f"v3/en/players/{player_id}/profile.json"
        data, error = self._make_request(endpoint)
        if error:
            return None, error
        return data, None

    def get_headshot_manifest(self):
        """
        Fetches the Sportradar XML manifest and returns a dictionary
        mapping player IDs to their image path.
        """
        # Note: The manifest URL might require an API key in a real-world scenario
        manifest_url = "https://api.sportradar.com/golf-images-t3/getty/pga/headshots/players/2025/manifest.xml"
        headshot_map = {}
        headers = {
            "accept": "application/json",
            "x-api-key": self.api_key
        }

         # --- DEBUGGING ---
        print("\n--- 1. Fetching Headshot Manifest ---")
        print(f"URL: {manifest_url}")
        # ---
        try:
            response = requests.get(manifest_url, headers=headers)
            response.raise_for_status()
            root = ET.fromstring(response.content)

            # Define the namespace found in the XML file's root element
            namespaces = {'ns': 'http://feed.elasticstats.com/schema/assets/manifest-v2.5.xsd'}

            # The XML structure is <players><player id="..."><links><link href="..." ...
            for asset_node in root.findall('.//ns:asset', namespaces):
                player_id = asset_node.get('player_id')
                original_link_node = None
                # Find all link nodes within the current asset
                for link_node in asset_node.findall("./ns:links/ns:link", namespaces):
                    # Check if the link's href contains 'original.jpg'
                    if 'original.jpg' in link_node.get('href', ''):
                        original_link_node = link_node
                        break # Stop searching once we've found it

                if player_id and original_link_node is not None:
                    href = original_link_node.get('href')
                    # Split the path and get the image-specific ID
                    # e.g., /pga/headshots/players/IMAGE_ID/original.jpg
                    image_id = href.split('/')[-2]
                    headshot_map[player_id] = image_id


            # --- DEBUGGING ---
            print(f"--- 2. Successfully Parsed Manifest ---")
            print(f"Found {len(headshot_map)} player headshot mappings.")
            # Print the first 5 entries to verify
            print("Example entries:", dict(list(headshot_map.items())[:5]))
            print("---------------------------------------\n")
            # ---

            return headshot_map, None

        except (requests.exceptions.RequestException, ET.ParseError) as e:
            print(f"--- ERROR in get_headshot_manifest ---")
            print(f"Error processing headshot manifest: {e}")
            print("---------------------------------------\n")
            return None, str(e)
