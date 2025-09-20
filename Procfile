web: gunicorn --worker-class gevent -w 1 --bind 0.0.0.0:$PORT run:app
worker: celery -A fantasy_league_app.celery worker --loglevel=info --pool=solo
beat: celery -A fantasy_league_app.celery beat --loglevel=info --scheduler redbeat.RedBeatScheduler