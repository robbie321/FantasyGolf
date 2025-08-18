from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_apscheduler import APScheduler
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO
import stripe

from .config import Config

from flask_mail import Mail # Import Mail


db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
csrf = CSRFProtect()
socketio = SocketIO()
login_manager = LoginManager()
login_manager.login_view = 'auth.login_choice'
scheduler = APScheduler()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    socketio.init_app(app)

    login_manager.init_app(app)

    # Initialize and start the scheduler
    if not scheduler.running:
        scheduler.init_app(app)
        scheduler.start()

    #  import from the renamed 'tasks.py' file.
    from .tasks import update_active_league_scores, settle_finished_leagues, send_deadline_reminders, update_player_buckets, reset_player_scores, finalize_finished_leagues

    if not scheduler.get_job('update_scores'):
        scheduler.add_job(
            id='update_scores',
            func=update_active_league_scores,
            args=[app],
            trigger='cron',
            day_of_week='thu-sun',  # Only run on Thursday, Friday, Saturday, Sunday
            hour='6-23',          # Only run between 6:00 AM and 11:59 PM
            minute='*/5'           # Runs every 2 minutes within the specified window
        )

    # --- Add the weekly job for resetting scores ---
    if not scheduler.get_job('reset_scores'):
        scheduler.add_job(
            id='reset_scores',
            func=reset_player_scores,
            args=[app],
            trigger='cron',
            day_of_week='wed',  # Run on Tuesday
            hour=20,             # Run at 5:00 AM
            minute=52
        )


    if not scheduler.get_job('update_buckets'):
        scheduler.add_job(
            id='update_buckets',
            func=update_player_buckets,
            args=[app],
            trigger='cron',
            day_of_week='mon', # Run on Mondays
            hour=13,           # Run at 3 PM (15:00)
            minute=32
        )

        # --- NEW: Add the weekly job for finalizing leagues ---
    if not scheduler.get_job('finalize_leagues'):
        scheduler.add_job(
            id='finalize_leagues',
            func=finalize_finished_leagues,
            args=[app],
            trigger='cron',
            day_of_week='mon',
            hour=13,
            minute=30
        )


        # Add the job for settling finished leagues (runs every 15 minutes)
    # if not scheduler.get_job('settle_leagues'):
    #     scheduler.add_job(
    #         id='settle_leagues',
    #         func=settle_finished_leagues,
    #         args=[app],
    #         trigger='interval',
    #         minutes=15
    #     )

     # Add the job for deadline reminders (runs every hour)
    if not scheduler.get_job('deadline_reminders'):
        scheduler.add_job(
            id='deadline_reminders',
            func=send_deadline_reminders,
            args=[app],
            trigger='interval',
            hours=1
        )

    app.jinja_env.globals.update(hasattr=hasattr)
    stripe.api_key = app.config['STRIPE_SECRET_KEY']
    mail.init_app(app)


    from . import models

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

    # Register Blueprints
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


    # --- Error Handlers ---
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback() # Roll back the session to prevent a broken state
        return render_template('errors/500.html'), 500

    return app
