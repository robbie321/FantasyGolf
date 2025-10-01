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
sess = Session()  # Flask-Session

def make_celery(app=None):
    """Create and configure Celery instance"""
    redis_url = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'

    celery = Celery(
        'fantasy_league_app',
        broker=redis_url,
        backend=redis_url,
        include=['fantasy_league_app.tasks']
    )

    # IMPORTANT: Configure Celery to load from celeryconfig.py
    celery.config_from_object('celeryconfig')

    # Basic configuration - beat schedule will be loaded from celeryconfig.py
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
        # Add debugging options
        task_track_started=True,
        task_send_sent_event=True,
    )

    if app is not None:
        # Configure tasks to run with app context
        class ContextTask(celery.Task):
            """Make celery tasks work with Flask app context."""
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)

        celery.Task = ContextTask

    return celery

# Create Celery instance without app initially
celery = make_celery()

# Login Manager setup
login_manager = LoginManager()
login_manager.login_view = 'auth.login_choice'
login_manager.session_protection = "strong"

# Rate Limiter - configure with storage URI and defaults
limiter = Limiter(
    key_func=get_remote_address,
)

def init_extensions(app):
    """Initialize all extensions with the Flask app"""
    from .config import Config

    # Initialize extensions with the app
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    socketio.init_app(app)
    cache.init_app(app)
    login_manager.init_app(app)
    Config.init_app(app)

    # ===== Initialize Flask-Session with Redis =====
    # Create Redis connection for sessions
    try:
        redis_url = app.config.get('redis_url')
        app.config['SESSION_REDIS'] = redis.from_url(redis_url)
        sess.init_app(app)
        app.logger.info(f"Flask-Session initialized with Redis: {redis_url}")
    except Exception as e:
        app.logger.error(f"Failed to initialize Flask-Session with Redis: {e}")
        # Fallback to filesystem sessions if Redis fails
        app.config['SESSION_TYPE'] = 'filesystem'
        sess.init_app(app)
        app.logger.warning("Flask-Session falling back to filesystem storage")
    # ===== End Flask-Session Initialization =====

    # Properly configure Celery with app context
    celery.conf.update(app.config)

    # Initialize rate limiter (just pass the app)
    limiter.init_app(app)

    # IMPORTANT: Explicitly set the beat schedule
    celery.conf.beat_schedule = app.config.get('beat_schedule', {})

    # Configure tasks to run with app context
    class ContextTask(celery.Task):
        """Make celery tasks work with Flask app context."""
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask