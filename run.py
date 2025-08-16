# run.py

from fantasy_league_app import create_app, db, socketio

app = create_app()

if __name__ == '__main__':
    socketio.run(app)