# run.py
import os
from fantasy_league_app import create_app, db, socketio
from fantasy_league_app.scripts import db_scripts
from dotenv import load_dotenv

# Set the environment variable directly in the script for foolproof local testing
os.environ['SCHEDULER_ENABLED'] = 'true'

if os.getenv('DYNO') is None:  # Only load .env locally
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

app = create_app()
app.cli.add_command(db_scripts)

if __name__ == '__main__':
    socketio.run(app)