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
from .config import Config
from celery import Celery
from celery.schedules import crontab
import mimetypes

# --- Extension Initialization ---
cache = Cache()
db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
csrf = CSRFProtect()
socketio = SocketIO()

# FIXED: Create Celery instance with better configuration
def make_celery(app=None):
    """Create and configure Celery instance"""
    redis_url = os.environ.get('REDISCLOUD_URL') or os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'

    celery = Celery(
        'fantasy_league_app',
        broker=redis_url,
        backend=redis_url,
        include=['fantasy_league_app.tasks']
    )

    # Update basic configuration
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


def create_app(config_class=Config):
    """
    Application factory function. Configures and returns the Flask app.
    """
    mimetypes.add_type('application/javascript', '.js')
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- Initialize Extensions with the App ---
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    socketio.init_app(app)
    cache.init_app(app)
    login_manager.init_app(app)

    # FIXED: Properly configure Celery with app context
    celery.conf.update(app.config)

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

    return app