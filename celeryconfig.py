# Replace your entire celeryconfig.py with this:

from celery.schedules import crontab
import os

# ONLY NEW FORMAT SETTINGS - NO CELERY_* PREFIXES!

# Redis configuration
redis_url = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'

# NEW FORMAT broker settings
broker_url = redis_url
result_backend = redis_url

# NEW FORMAT task settings
task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'UTC'
enable_utc = True
task_track_started = True
task_send_sent_event = True
broker_connection_retry_on_startup = True
broker_connection_retry = True
broker_connection_max_retries = 10

# Beat schedule - NEW FORMAT
beat_schedule = {
    'schedule-live-score-updates': {
        'task': 'fantasy_league_app.tasks.schedule_score_updates_for_the_week',
        'schedule': crontab(hour=14, minute=50, day_of_week='thu,fri,sat,sun'),
    },
    'reset-player-scores-weekly': {
        'task': 'fantasy_league_app.tasks.reset_player_scores',
        'schedule': crontab(hour=8, minute=0, day_of_week='wed'),
    },
    'send-deadline-reminders-hourly': {
        'task': 'fantasy_league_app.tasks.send_deadline_reminders',
        'schedule': crontab(minute=0),
    },
    'update-buckets-weekly': {
        'task': 'fantasy_league_app.tasks.update_player_buckets',
        'schedule': crontab(hour=10, minute=0, day_of_week='tuesday'),
    },
    'finalize-leagues-weekly': {
        'task': 'fantasy_league_app.tasks.finalize_finished_leagues',
        'schedule': crontab(hour=10, minute=30, day_of_week='monday'),
    },
    'check-for-fees-weekly': {
        'task': 'fantasy_league_app.tasks.check_and_queue_fee_collection',
        'schedule': crontab(hour=10, minute=0, day_of_week='thursday'),
    },
    'ensure-live-updates-running': {
        'task': 'fantasy_league_app.tasks.ensure_live_updates_are_running',
        'schedule': crontab(minute='*/1'),
    },
    'warm-caches-early-morning': {
        'task': 'fantasy_league_app.tasks.warm_critical_caches',
        'schedule': crontab(hour=5, minute=30),
    },
    'cleanup-stale-caches': {
        'task': 'fantasy_league_app.tasks.cleanup_expired_caches',
        'schedule': crontab(hour=2, minute=0),
    },
    # Debug task for testing (remove in production)
    'debug-test-every-2-minutes': {
        'task': 'fantasy_league_app.tasks.test_celery_connection',
        'schedule': crontab(minute='*/2'),
    },
    'cleanup-expired-verification-tokens': {
        'task': 'fantasy_league_app.tasks.cleanup_expired_verification_tokens',
        'schedule': crontab(hour=3, minute=0),  # Run daily at 3 AM
    },
}