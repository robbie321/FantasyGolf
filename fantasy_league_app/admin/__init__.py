# --- File: fantasy_league_app/admin/__init__.py (UPDATED - Template Folder Fix) ---

from flask import Blueprint

# Define the blueprint for admin-specific routes
# Correct template_folder to point to the root templates directory
# and then Flask will look for 'admin/' inside it.
admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')

# Import the routes to register them with the blueprint
from . import routes
