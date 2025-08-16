# run.py

from fantasy_league_app import create_app, db, socketio
from fantasy_league_app.scripts import db_scripts

app = create_app()
app.cli.add_command(db_scripts)

if __name__ == '__main__':
    socketio.run(app)