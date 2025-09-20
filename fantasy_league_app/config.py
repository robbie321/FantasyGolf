import os
from celery.schedules import crontab

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_super_secret_key_change_in_production'
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY') or 'a-different-super-secret-key'

    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = database_url or \
                              'postgresql://postgres:4bover2A!@localhost:5432/fantasy_league_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'uploads' # Still needed for the initial player CSV upload
    # Ensure the upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')


    # NEW: Stripe API Keys (use test keys for development)
    # You would get these from your Stripe Dashboard
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY') or 'pk_test_51Rt4YFAAtiw6IkD3q6QEunjHZZIlhDBfKvpefcbEHafQqqKV0En2Eu5QJaxomlGgk4CYA8Jk9nBH9hQu3Amsstf800E0bzTL1S'

    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY') or 'sk_test_51Rt4YFAAtiw6IkD3N2CNruve7zbaafKruqfMuJNeudIYNoL0eljrySxsoN9J2TGRDcYRCQFsRrz94roJF9hiaxXy00NwhqsECS'
    # For a real integration, you'd also need a webhook secret
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET') or 'whsec_YOUR_STRIPE_WEBHOOK_SECRET'

    STRIPE_PLATFORM_ACCOUNT_ID = os.environ.get('STRIPE_PLATFORM_ACCOUNT_ID')

    # Data Golf API
    DATA_GOLF_API_KEY = os.environ.get('DATA_GOLF_API_KEY') or '6194d71ab637acf3eb7800202456'

    SPORTRADAR_API_KEY = os.environ.get('SPORTRADAR_API_KEY') or 'svKy6tuJCkFOnKfLcDokEHXT9hIEOrAE4U4Uwokx'


     # --- Email Server Configuration ---
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.googlemail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME','robmalone7@gmail.com') # Your email address
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', 'wehh kfob ejkj isfm') # Your email app password
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)


    # --- Redis and Caching Configuration ---
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = os.environ.get('REDISCLOUD_URL', 'redis://localhost:6379/0')
    CACHE_DEFAULT_TIMEOUT = 300 # Default cache timeout in seconds (5 minutes)

       # --- VAPID Keys for Push Notifications ---

    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', 'public_key.pem') or 'MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEMikeN4Y56qUl9NKtb6vvneJs+0BC7DfKXJlCQGCY23qRKl5uJS36c3SWJqVVvv6eo+5rvgnNOb8Rv1dUKcdEZQ=='
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', 'private_key.pem') or 'MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgJEK++bJ3qsf4NV4jkIHX/RHFlzs0ZlaBe7AK8F865T6hRANCAAQyKR43hjnqpSX00q1vq++d4mz7QELsN8pcmUJAYJjbepEqXm4lLfpzdJYmpVW+/p6j7mu+Cc05vxG/V1Qpx0Rl'
    VAPID_CLAIM_EMAIL = os.environ.get('VAPID_CLAIM_EMAIL', 'mailto:rmalone7@gmail.com')


    TESTING_MODE_FLAG = 'testing_mode.flag'

    # Celery Beat Schedule
    CELERY_BEAT_SCHEDULE = {
        'schedule-live-score-updates': {
            'task': 'fantasy_league_app.tasks.schedule_score_updates_for_the_week',
            'schedule': crontab(hour=5, minute=0, day_of_week='thu,fri,sat,sun'),
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
            'schedule': crontab(minute='*/1'), # Runs every 15 minutes
        },
    }