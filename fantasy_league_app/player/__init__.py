from flask import Blueprint

# Define the blueprint for player-specific routes
player_bp = Blueprint('player', __name__, template_folder='../templates/player')

# Import the routes to register them
from . import routes