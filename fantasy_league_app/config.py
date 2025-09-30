import os
from celery.schedules import crontab
import logging
from logging.handlers import RotatingFileHandler

# Update your fantasy_league_app/config.py
# Replace the Config class with this cleaned version:

class Config:
    """Base configuration class with common settings"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_super_secret_key_change_in_production'
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY') or 'a-different-super-secret-key'

    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = database_url or \
                              'postgresql://postgres:4bover2A!@localhost:5432/fantasy_league_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_timeout': 20,
        'max_overflow': 0,
        'pool_size': 10
    }
    UPLOAD_FOLDER = 'uploads'
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Redis URL (used by production and some other configs)
    redis_url = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'

    RATELIMIT_STORAGE_URI = redis_url
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"

    # NEW FORMAT CELERY CONFIGURATION ONLY
    broker_url = redis_url
    result_backend = redis_url
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

    # REMOVED ALL OLD-STYLE CELERY_ SETTINGS!
    # No more CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP, etc.

    # Stripe Configuration
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY') or 'pk_test_51Rt4YFAAtiw6IkD3q6QEunjHZZIlhDBfKvpefcbEHafQqqKV0En2Eu5QJaxomlGgk4CYA8Jk9nBH9hQu3Amsstf800E0bzTL1S'
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY') or 'sk_test_51Rt4YFAAtiw6IkD3N2CNruve7zbaafKruqfMuJNeudIYNoL0eljrySxsoN9J2TGRDcYRCQFsRrz94roJF9hiaxXy00NwhqsECS'
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET') or 'whsec_YOUR_STRIPE_WEBHOOK_SECRET'
    STRIPE_PLATFORM_ACCOUNT_ID = os.environ.get('STRIPE_PLATFORM_ACCOUNT_ID')

    # API Keys
    DATA_GOLF_API_KEY = os.environ.get('DATA_GOLF_API_KEY') or '6194d71ab637acf3eb7800202456'
    SPORTRADAR_API_KEY = os.environ.get('SPORTRADAR_API_KEY') or 'svKy6tuJCkFOnKfLcDokEHXT9hIEOrAE4U4Uwokx'

    # Email Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.googlemail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME','robmalone7@gmail.com')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', 'wehh kfob ejkj isfm')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)

    # VAPID Keys for Push Notifications
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY') or 'BK7DkYrPmaEsLe-jgW-SarBoyhdq0kLXvUC3m-651GWGCY-lpsgdNDzezScSVkjAbipgMv7d99YDEU45Z06Rif0'
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY') or 'BJ0SBEH4WaLeyuHdCapquWjZ-ryd-JzMs_LlBuvg5WQ'
    VAPID_CLAIM_EMAIL = os.environ.get('VAPID_CLAIM_EMAIL', 'mailto:rmalone7@gmail.com')

    TESTING_MODE_FLAG = 'testing_mode.flag'

    # Default cache key prefix and timeouts (common for all environments)
    CACHE_KEY_PREFIX = 'ff_'
    CACHE_TIMEOUTS = {
        'player_scores': 180,      # 3 minutes - frequent updates during tournaments
        'league_data': 300,        # 5 minutes - moderate updates
        'user_data': 600,          # 10 minutes - infrequent updates
        'static_data': 3600,       # 1 hour - rarely changes
        'api_data': 900,           # 15 minutes - external API responses
        'leaderboards': 120,       # 2 minutes - tournament leaderboards
    }

    # Celery Beat Schedule - NEW FORMAT ONLY
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
            'schedule': crontab(hour=13, minute=30, day_of_week='monday'),
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
        'cleanup-push-subscriptions-weekly': {
        'task': 'fantasy_league_app.tasks.cleanup_old_push_subscriptions',
        'schedule': crontab(hour=2, minute=0, day_of_week='monday'),
        },
        'send-league-start-notifications': {
            'task': 'fantasy_league_app.tasks.send_league_start_notifications',
            'schedule': crontab(hour=8, minute=0),  # Daily at 8 AM
        },
        'send-rank-change-notifications': {
            'task': 'fantasy_league_app.tasks.send_rank_change_notifications',
            'schedule': crontab(minute='*/30'),  # Every 30 minutes during tournaments
        },
        'cleanup-push-subscriptions-weekly': {
        'task': 'fantasy_league_app.tasks.cleanup_old_push_subscriptions',
        'schedule': crontab(hour=2, minute=0, day_of_week='monday'),
        },
        'check-player-withdrawals-thursday': {
        'task': 'fantasy_league_app.tasks.substitute_withdrawn_players',
        'schedule': crontab(minute='*/15', hour='6-14', day_of_week='thursday'),  # Every 15 min, 6am-2pm UTC on Thursdays
        },
    }


    @staticmethod
    def init_app(app):
        """Initialize app-specific configuration"""

        # Security logging setup
        if not app.debug and not app.testing:
            # Create logs directory if it doesn't exist
            if not os.path.exists('logs'):
                os.mkdir('logs')

            # Security event logger
            security_handler = RotatingFileHandler(
                'logs/security.log',
                maxBytes=10240000,
                backupCount=10
            )
            security_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            ))
            security_handler.setLevel(logging.INFO)

            # Create security logger
            security_logger = logging.getLogger('security')
            security_logger.addHandler(security_handler)
            security_logger.setLevel(logging.INFO)


class DevelopmentConfig(Config):
    """Development configuration - uses simple cache for local development"""
    DEBUG = True

    # Use simple cache for local development (no Redis required)
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 300

    # REMOVED OLD FORMAT SETTINGS!
    # No more CELERY_BROKER_URL or CELERY_RESULT_BACKEND

    # NEW FORMAT ONLY: Override Redis URL for development
    # Since Redis is working on your machine, let's stick with Redis for development
    broker_url = 'redis://localhost:6379/0'
    result_backend = 'redis://localhost:6379/0'

    # If you want to use memory broker instead (loses tasks on restart):
    # broker_url = 'memory://'
    # result_backend = 'cache+memory://'

    # Override cache timeouts for faster development testing
    CACHE_TIMEOUTS = {
        'player_scores': 60,       # 1 minute in dev
        'league_data': 120,        # 2 minutes in dev
        'user_data': 300,          # 5 minutes in dev
        'static_data': 600,        # 10 minutes in dev
        'api_data': 300,           # 5 minutes in dev
        'leaderboards': 60,        # 1 minute in dev
    }


class ProductionConfig(Config):
    """Production configuration - uses Redis for caching"""
    DEBUG = False

    # Use Redis for production caching
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = Config.redis_url
    CACHE_DEFAULT_TIMEOUT = 300


class TestingConfig(Config):
    """Testing configuration - for running tests"""
    TESTING = True
    DEBUG = True

    # Use simple cache for testing (fast and isolated)
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 60

    # Use in-memory SQLite for testing
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False


# Configuration dictionary for easy selection
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}