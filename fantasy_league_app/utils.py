import json
from flask import current_app
from fantasy_league_app import db, mail
from fantasy_league_app.models import Player
from datetime import datetime, timedelta
from functools import wraps
from flask import redirect, url_for, request
from flask_login import current_user
from pywebpush import webpush, WebPushException
from .models import PushSubscription

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

def get_league_creation_status():
    """
    Checks the current time to determine if league creation is allowed and for which tours.
    All times are handled in UTC.
    """
    now = datetime.utcnow()
    # weekday(): Monday is 0, Sunday is 6.
    # Wednesday is 2, Thursday is 3, Monday is 0.
    weekday = now.weekday()

    # Define the cutoff times
    pga_cutoff_day = 2 # Wednesday
    pga_cutoff_hour = 18 # 6 PM UTC
    liv_cutoff_day = 3 # Thursday
    liv_cutoff_hour = 18 # 6 PM UTC
    reopen_day = 0 # Monday
    reopen_hour = 13 # 1:30 PM UTC -> 13.5
    reopen_minute = 30

    # --- Check for the weekend lockout period ---
    # Lockout starts Thursday at 6 PM UTC
    is_after_thursday_cutoff = (weekday == 3 and (now.hour >= 18))
    # Lockout includes all of Friday, Saturday, Sunday
    is_weekend = weekday in [4, 5, 6]
    # Lockout ends Monday at 1:30 PM UTC
    is_before_monday_reopen = (weekday == 0 and (now.hour < 13 or (now.hour == 13 and now.minute < 30)))

    if is_after_thursday_cutoff or is_weekend or is_before_monday_reopen:
        return {
            "is_creation_enabled": False,
            "available_tours": [],
            "message": "League creation is currently disabled. It will reopen on Monday at 1:30 PM UTC."
        }

    # --- If not in lockout, determine which tours are available ---
    available_tours = ['pga', 'euro', 'kft', 'alt']

    # Check if PGA/Euro/KFT deadline has passed (Wednesday 6 PM UTC)
    if weekday == 2 and now.hour >= 18:
        available_tours.remove('pga')
        available_tours.remove('euro')
        available_tours.remove('kft')

    return {
        "is_creation_enabled": True,
        "available_tours": available_tours,
        "message": ""
    }

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



def send_push_notification(user_id, title, body, icon=None):
    """
    Sends a push notification to all subscribed devices for a given user.
    """
    app = current_app._get_current_object()
    user_subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()

    if not user_subscriptions:
        print(f"No push subscriptions found for user {user_id}.")
        return

    message = json.dumps({
        "title": title,
        "body": body,
        "icon": icon or "/static/images/icons/icon-192x192.png"
    })

    # Construct the full path to your VAPID private key
    private_key_path = os.path.join(app.root_path, '..', app.config['VAPID_PRIVATE_KEY'])

    print(f"Sending push notification to user {user_id}: '{body}'")
    for sub in user_subscriptions:
        try:
            webpush(
                subscription_info=json.loads(sub.subscription_json),
                data=message,
                vapid_private_key=private_key_path,
                vapid_claims={"sub": f"mailto:{app.config['VAPID_CLAIM_EMAIL']}"}
            )
        except WebPushException as ex:
            print(f"WebPushException for user {user_id}: {ex}")
            # If the subscription is expired or invalid (404, 410), delete it
            if ex.response and ex.response.status_code in [404, 410]:
                db.session.delete(sub)

    db.session.commit()



def send_email(subject, recipients, html_body):
    """
    A utility function to send emails from the application.
    """
    try:
        msg = Message(subject, recipients=recipients, html=html_body)
        mail.send(msg)
        current_app.logger.info(f"Email sent successfully to {recipients}")
    except Exception as e:
        current_app.logger.error(f"Failed to send email to {recipients}: {e}")

