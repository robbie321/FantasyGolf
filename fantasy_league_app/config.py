import os
from celery.schedules import crontab
import logging
from logging.handlers import RotatingFileHandler
from datetime import timedelta

class Config:
    """Base configuration class with common settings"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_super_secret_key_change_in_production'
    WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY') or 'a-different-super-secret-key'

    # Database configuration
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

    # Redis URL
    redis_url = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'

    # ===== REDIS CONNECTION POOL SETTINGS =====
    REDIS_MAX_CONNECTIONS = 10  # Per web dyno
    REDIS_SOCKET_KEEPALIVE = True
    REDIS_SOCKET_CONNECT_TIMEOUT = 5
    REDIS_HEALTH_CHECK_INTERVAL = 30

    # ===== SESSION CONFIGURATION =====
    # Session Configuration
    SESSION_TYPE = 'redis'  # Using Redis for sessions (you already have it configured)
    SESSION_PERMANENT = True
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = 'fantasy_fairways_session:'
    PERMANENT_SESSION_LIFETIME = timedelta(days=31)  # Sessions last 31 days

    # Session Cookie Configuration (defaults to False for development)
    SESSION_COOKIE_NAME = 'fantasy_fairways_session'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = False  # Will be overridden in ProductionConfig
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_PATH = '/'

    # Remember Me Cookie Configuration
    REMEMBER_COOKIE_NAME = 'fantasy_fairways_remember'
    REMEMBER_COOKIE_DURATION = timedelta(days=365)  # Remember for 1 year
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = False  # Will be overridden in ProductionConfig
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    # ===== END SESSION CONFIGURATION =====

    UPLOAD_FOLDER = 'uploads'
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    RATELIMIT_STORAGE_URI = redis_url
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"

    # Celery configuration
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

    # Cache configuration
    CACHE_KEY_PREFIX = 'ff_'
    CACHE_TIMEOUTS = {
        'player_scores': 180,
        'league_data': 300,
        'user_data': 600,
        'static_data': 3600,
        'api_data': 900,
        'leaderboards': 120,
    }

    # Celery Beat Schedule
    beat_schedule = {
        # In config.py, change this:
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
            if not os.path.exists('logs'):
                os.mkdir('logs')

            security_handler = RotatingFileHandler(
                'logs/security.log',
                maxBytes=10240000,
                backupCount=10
            )
            security_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            ))
            security_handler.setLevel(logging.INFO)

            security_logger = logging.getLogger('security')
            security_logger.addHandler(security_handler)
            security_logger.setLevel(logging.INFO)


class DevelopmentConfig(Config):
    """Development configuration - sessions work without HTTPS"""
    DEBUG = True

    # Use simple cache for local development
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 300

    # Redis for sessions in development
    broker_url = 'redis://localhost:6379/0'
    result_backend = 'redis://localhost:6379/0'

    # ===== SESSION SECURITY - FALSE FOR DEVELOPMENT =====
    SESSION_COOKIE_SECURE = False  # Allow HTTP in development
    REMEMBER_COOKIE_SECURE = False  # Allow HTTP in development

    # Override cache timeouts for faster development testing
    CACHE_TIMEOUTS = {
        'player_scores': 60,
        'league_data': 120,
        'user_data': 300,
        'static_data': 600,
        'api_data': 300,
        'leaderboards': 60,
    }


class ProductionConfig(Config):
    """Production configuration - uses Redis and requires HTTPS"""
    DEBUG = False

    # Use Redis for production caching
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = Config.redis_url
    CACHE_DEFAULT_TIMEOUT = 300

    # ===== SESSION SECURITY - TRUE FOR PRODUCTION =====
    SESSION_COOKIE_SECURE = True  # Require HTTPS in production
    REMEMBER_COOKIE_SECURE = True  # Require HTTPS in production

class StagingConfig(Config):
    """Staging configuration - mirrors production but separate"""
    DEBUG = False
    TESTING = False

    # Use Redis for staging caching
    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = Config.redis_url
    CACHE_DEFAULT_TIMEOUT = 300

    # Session configuration - explicitly set for staging
    SESSION_TYPE = 'redis'
    SESSION_REDIS = None  # Will be set by init_extensions
    SESSION_PERMANENT = True
    SESSION_USE_SIGNER = True

    # Session security
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Make sure CSRF is enabled
    WTF_CSRF_ENABLED = True


class TestingConfig(Config):
    """Testing configuration - for running tests"""
    TESTING = True
    DEBUG = True

    # Use simple cache for testing
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 60

    # Use in-memory SQLite for testing
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False

    # ===== SESSION SECURITY - FALSE FOR TESTING =====
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


# Update config dictionary
config = {
    'development': DevelopmentConfig,
    'staging': StagingConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}