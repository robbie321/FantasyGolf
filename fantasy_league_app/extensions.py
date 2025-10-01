import os
from flask_caching import Cache
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_session import Session
from celery import Celery
from celery.schedules import crontab
import redis

# --- Extension Initialization ---
cache = Cache()
db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
csrf = CSRFProtect()
socketio = SocketIO()
sess = Session()

# ===== SHARED REDIS CONNECTION POOL =====
_redis_pool = None

def get_redis_pool():
    """Get or create the shared Redis connection pool"""
    global _redis_pool
    if _redis_pool is None:
        redis_url = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'

        # Create connection pool with conservative settings
        _redis_pool = redis.ConnectionPool.from_url(
            redis_url,
            max_connections=10,  # Limit total connections from Flask app
            socket_keepalive=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
            decode_responses=False  # Flask-Session needs bytes
        )
    return _redis_pool

def get_redis_client():
    """Get a Redis client using the shared connection pool"""
    return redis.Redis(connection_pool=get_redis_pool())
# ===== END SHARED REDIS CONNECTION POOL =====

def make_celery(app=None):
    """Create and configure Celery instance"""
    redis_url = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'

    celery = Celery(
        'fantasy_league_app',
        broker=redis_url,
        backend=redis_url,
        include=['fantasy_league_app.tasks']
    )

    celery.config_from_object('celeryconfig')

    celery.conf.update(
        broker_url=redis_url,
        result_backend=redis_url,
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        timezone='UTC',
        enable_utc=True,
        broker_connection_retry_on_startup=True,
        broker_connection_retry=True,
        broker_connection_max_retries=10,
        task_track_started=True,
        task_send_sent_event=True,
        broker_pool_limit=5,  # Limit Celery broker connections
        redis_max_connections=5,  # Limit Celery result backend connections
    )

    if app is not None:
        class ContextTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)
        celery.Task = ContextTask

    return celery

celery = make_celery()

# Login Manager setup
login_manager = LoginManager()
login_manager.login_view = 'auth.login_choice'
login_manager.session_protection = "strong"

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)

def init_extensions(app):
    """Initialize all extensions with the Flask app"""
    from .config import Config

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    socketio.init_app(app)
    login_manager.init_app(app)
    Config.init_app(app)

    # ===== Initialize Flask-Session with SHARED Redis =====
    try:
        app.config['SESSION_REDIS'] = get_redis_client()
        sess.init_app(app)
        app.logger.info("✅ Flask-Session initialized with shared Redis pool")
    except Exception as e:
        app.logger.error(f"❌ Flask-Session Redis init failed: {e}")
        app.config['SESSION_TYPE'] = 'filesystem'
        sess.init_app(app)
        app.logger.warning("⚠️ Flask-Session using filesystem fallback")

    # ===== Initialize Cache with SHARED Redis =====
    try:
        if app.config.get('CACHE_TYPE') == 'RedisCache':
            redis_url = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
            app.config['CACHE_REDIS_URL'] = redis_url
            # Use shared connection pool for cache
            app.config['CACHE_OPTIONS'] = {
                'connection_pool': get_redis_pool()
            }
            app.logger.info("✅ Flask-Caching initialized with shared Redis pool")
        cache.init_app(app)
    except Exception as e:
        app.logger.error(f"❌ Cache initialization error: {e}")

    celery.conf.update(app.config)
    limiter.init_app(app)
    celery.conf.beat_schedule = app.config.get('beat_schedule', {})

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery.Task = ContextTask