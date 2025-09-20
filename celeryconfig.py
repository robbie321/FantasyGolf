# celeryconfig.py
from celery.schedules import crontab
import os

# Redis configuration
redis_url = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
broker_url = redis_url
result_backend = redis_url

# Beat schedule
beat_schedule = {
    'ensure-live-updates-running': {
        'task': 'fantasy_league_app.tasks.ensure_live_updates_are_running',
        'schedule': crontab(minute='*/1'),
    },
    # Add other tasks if needed
}

timezone = 'UTC'