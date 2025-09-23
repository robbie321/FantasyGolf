import os
import stripe
from flask import Flask, render_template
from flask_caching import Cache
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO
from flask_mail import Mail
from .config import config, Config
from celery import Celery
from celery.schedules import crontab
import mimetypes
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from fantasy_league_app.push import push_bp, push_service, create_notification_templates


# --- Extension Initialization ---
cache = Cache()
db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
csrf = CSRFProtect()
socketio = SocketIO()
limiter = Limiter(key_func=get_remote_address)

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

login_manager = LoginManager()
login_manager.login_view = 'auth.login_choice'
login_manager.session_protection = "strong"

_app_instance = None


def create_app(config_name=None):
    """
    Application factory function. Configures and returns the Flask app.
    """
    mimetypes.add_type('application/javascript', '.js')
    app = Flask(__name__)

    # Determine which configuration to use
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    # Support both old and new ways of calling create_app
    if isinstance(config_name, type) and hasattr(config_name, '__name__'):
        # Old way: create_app(Config) - use the class directly
        app.config.from_object(config_name)
    else:
        # New way: create_app('development') - use config dictionary
        app.config.from_object(config[config_name])

    # --- Initialize Extensions with the App ---
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    socketio.init_app(app)
    cache.init_app(app)
    login_manager.init_app(app)
    Config.init_app(app)

    # Properly configure Celery with app context
    celery.conf.update(app.config)

    # Initialize rate limiter
    limiter = Limiter(
    app,
    storage_uri=os.environ.get('REDIS_URL', 'redis://localhost:6379/1'),
    default_limits=["200 per day", "50 per hour"]
    )

    # IMPORTANT: Explicitly set the beat schedule
    from celery.schedules import crontab
    celery.conf.beat_schedule = app.config.get('beat_schedule', {})

    # Configure tasks to run with app context
    class ContextTask(celery.Task):
        """Make celery tasks work with Flask app context."""
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask

    # Import models and define user loaders before registering blueprints
    from .models import User, Club, SiteAdmin

    @login_manager.user_loader
    def load_user(user_id_string):
        """
        Loads a user from the session. The user_id_string is formatted
        as 'type-id' (e.g., 'user-1', 'club-3', 'admin-2').
        """
        print(f"\n--- DEBUG: Unified user_loader called with ID string: {user_id_string} ---")
        if user_id_string is None or '-' not in user_id_string:
            return None

        user_type, user_id = user_id_string.split('-', 1)

        try:
            user_id = int(user_id)
        except ValueError:
            return None

        if user_type == 'user':
            print(f"DEBUG: Loading User with ID: {user_id}")
            return User.query.get(user_id)
        elif user_type == 'club':
            print(f"DEBUG: Loading Club with ID: {user_id}")
            return Club.query.get(user_id)
        elif user_type == 'admin':
            print(f"DEBUG: Loading SiteAdmin with ID: {user_id}")
            return SiteAdmin.query.get(user_id)

        return None

    # --- Register Blueprints ---
    from .main.routes import main_bp
    from .auth.routes import auth_bp
    from .league.routes import league_bp
    from .admin.routes import admin_bp
    from .player.routes import player_bp
    from .api.routes import api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(league_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(player_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    #Register push notification blueprint
    app.register_blueprint(push_bp)

    #Initialize push notification service
    push_service.init_app(app)

    #Create notification templates on first run
    with app.app_context():
        try:
            create_notification_templates()
        except Exception as e:
            app.logger.error(f"Failed to create notification templates: {e}")

    return app


def get_app():
    global _app_instance
    if _app_instance is None:
        _app_instance = create_app()
    return _app_instance


def get_current_environment():
    """Helper function to get current environment"""
    return os.environ.get('FLASK_ENV', 'development')


def is_development():
    """Check if running in development mode"""
    return get_current_environment() == 'development'


def is_production():
    """Check if running in production mode"""
    return get_current_environment() == 'production'


def is_testing():
    """Check if running in testing mode"""
    return get_current_environment() == 'testing'