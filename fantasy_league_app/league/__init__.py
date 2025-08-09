from flask import Blueprint

league_bp = Blueprint('league', __name__, template_folder='templates')

from . import routes
