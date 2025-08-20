# download_headshots.py

import os
import requests
from bs4 import BeautifulSoup
from fantasy_league_app import create_app, db
from fantasy_league_app.models import Player

# --- CONFIGURATION ---
SAVE_DIRECTORY = "fantasy_league_app/static/images/headshots"
# --- END CONFIGURATION ---

def scrape_and_save_headshots():
    """
    Scrapes DataGolf player profile pages for headshot images and saves them locally.
    """
    app = create_app()
    with app.app_context():
        # 1. Create the save directory if it doesn't exist
        if not os.path.exists(SAVE_DIRECTORY):
            os.makedirs(SAVE_DIRECTORY)
            print(f"Created directory: {SAVE_DIRECTORY}")

        # 2. Get all players from the database
        players = Player.query.all()
        if not players:
            print("No players found in the database. Please add players first.")
            return

        print(f"Found {len(players)} players. Starting download process...")

        # 3. Loop through each player
        for player in players:
            if not player.dg_id:
                continue

            # Define the local path for the image
            image_filename = f"{player.dg_id}.png"
            local_image_path = os.path.join(SAVE_DIRECTORY, image_filename)

            # Check if the image already exists to avoid re-downloading
            if os.path.exists(local_image_path):
                print(f"Skipping {player.full_name()}: Headshot already exists.")
                continue

            # 4. Construct the profile URL and fetch the page
            profile_url = f"https://datagolf.com/player-profiles?dg_id={player.dg_id}"

            try:
                print(f"Fetching profile for {player.full_name()}...")
                response = requests.get(profile_url, timeout=10)
                response.raise_for_status()

                # 5. Parse the HTML and find the image tag
                soup = BeautifulSoup(response.content, 'html.parser')
                img_tag = soup.find('img', class_='player-pic')

                if not img_tag or not img_tag.get('src'):
                    print(f"Could not find headshot for {player.full_name()}.")
                    continue

                # 6. Construct the full image URL and download the image
                image_url = f"https://datagolf.com{img_tag['src']}"
                image_response = requests.get(image_url, stream=True)
                image_response.raise_for_status()

                # 7. Save the image to the local directory
                with open(local_image_path, 'wb') as f:
                    for chunk in image_response.iter_content(chunk_size=8192):
                        f.write(chunk)

                print(f"Successfully downloaded headshot for {player.full_name()} to {local_image_path}")

            except requests.exceptions.RequestException as e:
                print(f"Error fetching data for {player.full_name()}: {e}")
            except Exception as e:
                print(f"An unexpected error occurred for {player.full_name()}: {e}")

        print("\n--- Headshot download process finished. ---")

if __name__ == '__main__':
    scrape_and_save_headshots()