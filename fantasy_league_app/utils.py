from flask import current_app
from fantasy_league_app import db, mail
from fantasy_league_app.models import Player

from functools import wraps
from flask import redirect, url_for, request
from flask_login import current_user

import os

from flask_mail import Message

def password_reset_required(f):
    """
    A decorator to ensure a user who needs a password reset is redirected
    to the change password page.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if the user is authenticated and if the reset flag is set
        if current_user.is_authenticated and getattr(current_user, 'password_reset_required', False):
            # Allow access to the password change page itself and logout
            if request.endpoint not in ['auth.force_change_password', 'auth.logout', 'static']:
                return redirect(url_for('auth.force_change_password'))
        return f(*args, **kwargs)
    return decorated_function

def safe_int_score(value):
    if value == 'E':
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0

def safe_float_odds(value):
    try:
        clean_value = str(value).replace(',', '').replace('$', '').strip()
        return float(clean_value)
    except (ValueError, TypeError):
        return 0.0

def parse_player_name_from_display(player_str):
    return player_str.split(' (')[0].strip()

def get_player_by_full_name(full_name):
    name_parts = full_name.split(' ', 1)
    if len(name_parts) == 2:
        name, surname = name_parts
        return Player.query.filter_by(name=name, surname=surname).first()
    return None

def get_all_players_for_dropdown():
    players = Player.query.order_by(Player.name, Player.surname).all()
    return [f'{p.full_name()} ({p.odds:.2f})' for p in players]


def is_testing_mode_active():
    """Checks if the testing mode flag file exists."""
    flag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', current_app.config['TESTING_MODE_FLAG'])
    return os.path.exists(flag_path)


def send_entry_confirmation_email(user, league):
    """Sends an email to a user confirming their league entry."""
    msg = Message('League Entry Confirmation',
                  sender=current_app.config['MAIL_DEFAULT_SENDER'],
                  recipients=[user.email])
    msg.body = f"""Hi {user.full_name},

This email confirms your entry into the league: "{league.name}".

The entry deadline is {league.entry_deadline.strftime('%d %b %Y at %H:%M')} UTC. You can edit your entry until this time.

Good luck!
"""
    mail.send(msg)

def send_winner_notification_email(league):
    """Sends an email to all participants announcing the winner."""
    winner = league.winner
    if not winner:
        return

    recipients = [entry.user.email for entry in league.entries]
    if not recipients:
        return

    msg = Message(f'The Winner of "{league.name}" has been announced!',
                  sender=current_app.config['MAIL_DEFAULT_SENDER'],
                  recipients=recipients)
    msg.body = f"""The results are in for the league: "{league.name}"!

The winner is: {winner.full_name}

Congratulations to the winner and thank you to everyone who participated.
"""
    mail.send(msg)

