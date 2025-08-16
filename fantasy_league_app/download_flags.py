import os
import requests
import xml.etree.ElementTree as ET
import time # <-- 1. IMPORT THE TIME MODULE

# --- Add project directory to Python's path ---
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Import the Config class to access the API key ---
from fantasy_league_app.config import Config

# --- Configuration ---
MANIFEST_URL = "https://api.sportradar.us/flags-images-t3/sr/country-flags/flags/manifest.xml"
BASE_IMAGE_URL = "https://api.sportradar.us/flags-images-t3/sr/country-flags/flags"
SAVE_DIRECTORY = os.path.join('fantasy_league_app', 'static', 'images', 'flags')

# --- Load API Key from your config file ---
API_KEY = Config.SPORTRADAR_API_KEY

def download_country_flags():
    """
    Fetches the Sportradar XML manifest for country flags, downloads the
    h250-max-resize.png version of each flag, and saves it locally.
    """
    if not API_KEY:
        print("ERROR: SPORTRADAR_API_KEY not found in config.py. Please add it.")
        return

    print("--- Starting Country Flag Download Script ---")

    os.makedirs(SAVE_DIRECTORY, exist_ok=True)
    print(f"Saving flags to: {SAVE_DIRECTORY}")

    headers = {
        'accept': 'application/xml',
        'x-api-key': API_KEY
    }

    try:
        print(f"Fetching manifest from: {MANIFEST_URL}")
        response = requests.get(MANIFEST_URL, headers=headers)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        namespaces = {'ns': 'http://feed.elasticstats.com/schema/assets/manifest-v2.5.xsd'}
        flags_found = 0

        for asset_node in root.findall('.//ns:asset', namespaces):
            asset_id = asset_node.get('id')
            ref_node = asset_node.find("./ns:refs/ns:ref", namespaces)

            if asset_id and ref_node is not None:
                country_code = ref_node.get('iso_country_code')
                if not country_code:
                    continue

                image_url = f"{BASE_IMAGE_URL}/{asset_id}/h250-max-resize.png"
                save_path = os.path.join(SAVE_DIRECTORY, f"{country_code}.png")

                print(f"Downloading {country_code} from {image_url}...")
                image_response = requests.get(image_url, stream=True, headers=headers)
                image_response.raise_for_status()

                with open(save_path, 'wb') as f:
                    for chunk in image_response.iter_content(chunk_size=8192):
                        f.write(chunk)

                flags_found += 1

                # --- 2. ADD A 1-SECOND DELAY ---
                time.sleep(1) # Pause for 1 second to respect API rate limits

        print(f"\n--- Download Complete ---")
        print(f"Successfully downloaded {flags_found} flags.")

    except (requests.exceptions.RequestException, ET.ParseError) as e:
        print(f"\n--- An Error Occurred ---")
        print(f"Error: {e}")

if __name__ == '__main__':
    download_country_flags()
