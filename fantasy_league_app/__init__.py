import os
import stripe
from flask import Flask, render_template
from flask_caching import Cache
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_apscheduler import APScheduler
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO
from flask_mail import Mail

from .config import Config

# --- Extension Initialization ---
# These objects are created here so they can be imported by other parts of the app
cache = Cache()
db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
csrf = CSRFProtect()
socketio = SocketIO()
login_manager = LoginManager()
login_manager.login_view = 'auth.login_choice' # Redirects unauthenticated users to the login choice page
scheduler = APScheduler()

def create_app(config_class=Config):
    """
    Application factory function. Configures and returns the Flask app.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- Initialize Extensions with the App ---
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    socketio.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    cache.init_app(app)

    # --- Import Models and Tasks ---
    # These are imported here to avoid circular import errors
    from . import models
    from .tasks import (
        update_player_scores,
        reset_player_scores,
        update_player_buckets,
        finalize_finished_leagues,
        send_deadline_reminders
    )

    # --- User Loader for Flask-Login ---
    @login_manager.user_loader
    def load_user(user_id_string):
        try:
            parts = user_id_string.split('-')
            user_id = int(parts[0])
            user_type = parts[1]
        except (ValueError, IndexError):
            return None

        if user_type == 'user':
            return models.User.query.get(user_id)
        elif user_type == 'club':
            return models.Club.query.get(user_id)
        elif user_type == 'site_admin':
            return models.SiteAdmin.query.get(user_id)
        return None

    # --- Register Blueprints ---
    from .main import main_bp
    from .auth import auth_bp
    from .league import league_bp
    from .upload import upload_bp
    from .admin import admin_bp
    from .api import api_bp
    from .player import player_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(league_bp, url_prefix='/league')
    app.register_blueprint(upload_bp, url_prefix='/upload')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(player_bp, url_prefix='/player')

    # --- Jinja Globals and Stripe API Key ---
    app.jinja_env.globals.update(hasattr=hasattr, getattr=getattr)
    stripe.api_key = app.config['STRIPE_SECRET_KEY']

    # --- Scheduler Setup ---
    # This block is placed at the end of the factory to ensure the app is fully configured
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        if os.environ.get("SCHEDULER_ENABLED", "false").lower() == "true":

            # Add all scheduled jobs
            # if not scheduler.get_job('update_scores'):
            #     scheduler.add_job(id='update_scores', func=update_active_league_scores, args=[app], trigger='interval',
            #     minutes=1)
            if not scheduler.get_job('update_player_scores'):
                scheduler.add_job(
                id='update_player_scores',
                func=update_player_scores, # Use the new function
                args=[app],
                trigger='interval',
                minutes=1
            )
    # trigger='cron', day_of_week='thu-sun', hour='6-23', minute='*/1')

            if not scheduler.get_job('reset_scores'):
                scheduler.add_job(id='reset_scores', func=reset_player_scores, args=[app], trigger='cron', day_of_week='wed', hour=23, minute=59)

            if not scheduler.get_job('update_buckets'):
                scheduler.add_job(id='update_buckets', func=update_player_buckets, args=[app], trigger='cron', day_of_week='mon', hour=14, minute=0)

            if not scheduler.get_job('finalize_leagues'):
                scheduler.add_job(id='finalize_leagues', func=finalize_finished_leagues, args=[app], trigger='cron', day_of_week='mon', hour=10, minute=42)

            if not scheduler.get_job('deadline_reminders'):
                scheduler.add_job(id='deadline_reminders', func=send_deadline_reminders, args=[app], trigger='interval', hours=1)

            # CRITICAL: Start the scheduler
            if not scheduler.running:
                scheduler.start()
                print("--- SCHEDULER HAS BEEN STARTED. ---")
        else:
            print("--- SCHEDULER IS DISABLED. Set SCHEDULER_ENABLED=true in your environment to run background tasks. ---")

    # --- Error Handlers ---
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    return app