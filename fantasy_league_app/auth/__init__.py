# --- File: fantasy_league_app/auth/__init__.py (UPDATED - Template Folder Fix) ---

from flask import Blueprint

# Define the blueprint for auth-specific routes
# Correct template_folder to point to the root templates directory
# and then Flask will look for 'auth/' inside it.
# This path means: go up one directory from 'auth/' (to 'fantasy_league_app/')
# then go into 'templates/auth/'.
auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')

# Import the routes to register them with the blueprint
from . import routes
