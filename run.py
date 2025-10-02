# run.py
import os
from dotenv import load_dotenv

# Load .env file FIRST, before anything else
# This only loads if .env file exists (local development)
load_dotenv()

# Now import app after env vars are loaded
from fantasy_league_app import create_app, db, socketio
from fantasy_league_app.scripts import db_scripts

# Set the environment variable directly in the script for foolproof local testing
os.environ['SCHEDULER_ENABLED'] = 'true'

app = create_app()
app.cli.add_command(db_scripts)

if __name__ == '__main__':
    socketio.run(app)