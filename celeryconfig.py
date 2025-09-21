# celeryconfig.py
from celery.schedules import crontab
import os

# Redis configuration
redis_url = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
broker_url = redis_url
result_backend = redis_url

# Beat schedule
beat_schedule = {
    'schedule-live-score-updates': {
            'task': 'fantasy_league_app.tasks.schedule_score_updates_for_the_week',
            'schedule': crontab(
                minute='*/1'
                # hour=14, minute=50, day_of_week='thu,fri,sat,sun'
            ),
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
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
        },


}

timezone = 'UTC'