# fantasy_league_app/push/__init__.py

from flask import Blueprint
import os

# Import the main push routes
from .routes import push_bp

# Import test routes
try:
    from .test_routes import test_bp
    HAS_TEST_ROUTES = True
except ImportError:
    HAS_TEST_ROUTES = False
    test_bp = None

def init_push(app):
    """Initialize push notification blueprints"""

    # Register main push API routes
    app.register_blueprint(push_bp)

    # Enable test routes if:
    # 1. Test routes exist
    # 2. Either DEBUG mode OR ENABLE_PUSH_TEST env var is set
    enable_test = app.debug or os.environ.get('ENABLE_PUSH_TEST', 'false').lower() == 'true'

    if HAS_TEST_ROUTES and enable_test:
        app.register_blueprint(test_bp)
        app.logger.info('✅ Push notification test dashboard enabled at /push-test')
    elif HAS_TEST_ROUTES:
        app.logger.info('ℹ️ Push test routes available but disabled (set ENABLE_PUSH_TEST=true to enable)')

    app.logger.info('✅ Push notification routes registered')