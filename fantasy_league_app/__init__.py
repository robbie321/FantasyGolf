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
# All extension objects are created here in the global scope.
cache = Cache()
db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
csrf = CSRFProtect()
socketio = SocketIO()
celery = Celery(__name__, broker=Config.broker_url)

login_manager = LoginManager()
login_manager.login_view = 'auth.login_choice' # Main login page
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

    celery.conf.update(app.config)

    # Celery Beat Schedule
    celery.conf.beat_schedule = {
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
    }

    print("\n--- STRIPE KEY CHECK (on app start) ---")
    print(f"STRIPE_PUBLIC_KEY loaded: {app.config.get('STRIPE_PUBLIC_KEY')}")
    print(f"STRIPE_SECRET_KEY loaded: {app.config.get('STRIPE_SECRET_KEY')}")
    print("---------------------------------------\n")

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