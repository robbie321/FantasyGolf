web: gunicorn --worker-class gevent -w 1 --bind 0.0.0.0:$PORT run:app
worker: celery -A run.celery worker --loglevel=info
beat: celery -A run.celery beat --loglevel=info