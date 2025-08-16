# fantasy_league_app/scripts.py

import click
from flask.cli import with_appcontext
from .models import User
from . import db

# This creates a command group named 'db_scripts'
@click.group(name='db_scripts')
def db_scripts():
    """Custom database scripts."""
    pass

@db_scripts.command(name='make_admin')
@click.argument('email')
@with_appcontext
def make_admin(email):
    """Makes a user a site admin by their email."""
    user = User.query.filter_by(email=email).first()
    if user:
        user.is_site_admin = True
        db.session.commit()
        print(f"Success! User {user.email} is now a site admin.")
    else:
        print(f"Error: Could not find user with email {email}.")

# You can add more commands here!
# For example:
# @db_scripts.command(name='delete_league')
# @click.argument('league_id')
# @with_appcontext
# def delete_league(league_id):
#     # ... your logic here ...