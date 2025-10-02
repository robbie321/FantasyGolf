# fantasy_league_app/push/__init__.py
# Update this file to include test routes

from flask import Blueprint

# Import the main push routes
from .routes import push_bp

# Import test routes (create the test_routes.py file)
try:
    from .test_routes import test_bp
    HAS_TEST_ROUTES = True
except ImportError:
    HAS_TEST_ROUTES = False

def init_push(app):
    """Initialize push notification blueprints"""

    # Register main push API routes
    app.register_blueprint(push_bp)

    # Register test routes (only in development/testing)
    if HAS_TEST_ROUTES and (app.debug or app.config.get('TESTING')):
        app.register_blueprint(test_bp)
        app.logger.info('✅ Push notification test dashboard enabled at /push-test')

    app.logger.info('✅ Push notification routes registered')