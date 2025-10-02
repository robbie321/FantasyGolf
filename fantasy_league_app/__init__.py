import os
import stripe
from flask import Flask, render_template
import mimetypes
from .cli import register_cli_commands

# Import extensions from the new extensions file
from .extensions import (
    cache, db, migrate, mail, csrf, socketio, login_manager,
    celery, limiter, init_extensions
)
from .config import config, Config

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

    # Initialize all extensions
    init_extensions(app)

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
    app.register_blueprint(league_bp, url_prefix='/league')
    app.register_blueprint(admin_bp)
    app.register_blueprint(player_bp)
    app.register_blueprint(api_bp, url_prefix='/api')


    from fantasy_league_app.push import init_push
    init_push(app)

    # DEBUG: Print all registered routes
    if app.debug or os.environ.get('ENABLE_PUSH_TEST'):
        print("\n=== REGISTERED ROUTES ===")
        for rule in app.url_map.iter_rules():
            if 'push' in str(rule):
                print(f"{rule.methods} {rule.rule} -> {rule.endpoint}")
        print("=== END ROUTES ===\n")

    # Register CLI commands
    register_cli_commands(app)

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