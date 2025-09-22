import json
from fantasy_league_app import db, mail
from fantasy_league_app.models import Player
from datetime import datetime, timedelta
from functools import wraps
from flask import redirect, url_for, request, current_app
from flask_mail import Message
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


def send_email_verification(user):
    """Send email verification email to user"""

    # Generate verification URL
    verification_url = url_for(
        'auth.verify_email',
        token=user.email_verification_token,
        _external=True
    )

    # Email subject and body
    subject = "Verify Your Email Address - Fantasy Golf"

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #006a4e, #3498db); padding: 2rem; text-align: center;">
            <h1 style="color: white; margin: 0;">Fantasy Golf</h1>
        </div>

        <div style="padding: 2rem; background: white;">
            <h2 style="color: #006a4e;">Welcome, {user.full_name}!</h2>

            <p>Thank you for creating your Fantasy Golf account. To complete your registration and start playing, please verify your email address.</p>

            <div style="text-align: center; margin: 2rem 0;">
                <a href="{verification_url}"
                   style="background: #006a4e; color: white; padding: 1rem 2rem; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    Verify Email Address
                </a>
            </div>

            <p style="color: #666; font-size: 0.9rem;">
                If the button doesn't work, copy and paste this link into your browser:<br>
                <a href="{verification_url}" style="color: #006a4e; word-break: break-all;">
                    {verification_url}
                </a>
            </p>

            <p style="color: #666; font-size: 0.9rem; margin-top: 2rem;">
                This verification link will expire in 24 hours. If you didn't create this account, please ignore this email.
            </p>
        </div>

        <div style="background: #f8f9fa; padding: 1rem; text-align: center; color: #666; font-size: 0.8rem;">
            <p>© 2025 Fantasy Golf. All rights reserved.</p>
        </div>
    </div>
    """

    text_body = f"""
    Welcome to Fantasy Golf, {user.full_name}!

    Thank you for creating your account. To complete your registration, please verify your email address by clicking the link below:

    {verification_url}

    This link will expire in 24 hours. If you didn't create this account, please ignore this email.

    Thanks,
    The Fantasy Golf Team
    """

    try:
        msg = Message(
            subject=subject,
            recipients=[user.email],
            html=html_body,
            body=text_body
        )

        # Add security headers for better deliverability and security
        msg.extra_headers = {
            'List-Unsubscribe': f'<mailto:unsubscribe@fantasyfairway.ie?subject=Unsubscribe>',
            'Reply-To': current_app.config['MAIL_DEFAULT_SENDER'],
            'X-Auto-Response-Suppress': 'OOF, DR, NDR, RN, NRN',
            'X-Priority': '3',
            'X-MSMail-Priority': 'Normal',
            'X-Mailer': 'Fantasy Golf Application'
        }

        mail.send(msg)

        # Update the sent timestamp
        user.email_verification_sent_at = datetime.utcnow()
        db.session.commit()

        current_app.logger.info(f"Verification email sent to {user.email}")
        return True

    except Exception as e:
        current_app.logger.error(f"Failed to send verification email to {user.email}: {str(e)}")
        # Don't expose detailed error to user for security
        return False

def send_email_verification_success(user):
    """Send confirmation email after successful verification"""

    subject = "Email Verified - Welcome to Fantasy Golf!"

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #27ae60, #2ecc71); padding: 2rem; text-align: center;">
            <h1 style="color: white; margin: 0;">🎉 Email Verified!</h1>
        </div>

        <div style="padding: 2rem; background: white;">
            <h2 style="color: #27ae60;">Welcome to Fantasy Golf, {user.full_name}!</h2>

            <p>Your email address has been successfully verified. You can now:</p>

            <ul style="color: #333; line-height: 1.6;">
                <li>Join fantasy golf leagues</li>
                <li>Create your own leagues</li>
                <li>Compete with friends and other players</li>
                <li>Track live tournament scores</li>
            </ul>

            <div style="text-align: center; margin: 2rem 0;">
                <a href="{url_for('auth.login_choice', _external=True)}"
                   style="background: #27ae60; color: white; padding: 1rem 2rem; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                    Start Playing Now
                </a>
            </div>

            <p style="color: #666;">
                If you have any questions, feel free to contact our support team.
            </p>
        </div>

        <div style="background: #f8f9fa; padding: 1rem; text-align: center; color: #666; font-size: 0.8rem;">
            <p>© 2025 Fantasy Golf. All rights reserved.</p>
        </div>
    </div>
    """

    try:
        msg = Message(
            subject=subject,
            recipients=[user.email],
            html=html_body
        )
        mail.send(msg)
        current_app.logger.info(f"Welcome email sent to {user.email}")

    except Exception as e:
        current_app.logger.error(f"Failed to send welcome email to {user.email}: {e}")

def check_email_verification_required(user):
    """Check if user needs email verification before login"""
    return not user.email_verified


def is_valid_email_domain(email):
    """Check if email domain is allowed"""

    # List of blocked domains (disposable email services)
    blocked_domains = [
        '10minutemail.com',
        'tempmail.org',
        'guerrillamail.com',
        'mailinator.com',
        'throwaway.email',
        'temp-mail.org',
        'getnada.com',
        'tempail.com',
        'dispostable.com',
        'yopmail.com'
    ]

    try:
        domain = email.split('@')[1].lower()
        return domain not in blocked_domains
    except (IndexError, AttributeError):
        return False

def validate_email_security(email):
    """Comprehensive email validation for security"""

    if not email or '@' not in email:
        return False, "Invalid email format"

    if not is_valid_email_domain(email):
        return False, "Email domain not allowed"

    # Check for suspicious patterns
    if email.count('@') > 1:
        return False, "Invalid email format"

    # Check for extremely long emails (potential attack)
    if len(email) > 320:  # RFC 5321 limit
        return False, "Email address too long"

    return True, "Valid email"


def send_rank_change_email(user_id, subject, message, league_name):
    """Send rank change notification email to user"""
    try:
        from .models import User

        user = User.query.get(user_id)
        if not user or not user.email:
            current_app.logger.warning(f"Cannot send rank change email - user {user_id} not found or no email")
            return False

        # Create HTML email template
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #006a4e, #3498db); padding: 2rem; text-align: center;">
                <h1 style="color: white; margin: 0;">🏌️ Fantasy Golf Update</h1>
            </div>

            <div style="padding: 2rem; background: white;">
                <h2 style="color: #006a4e;">Hi {user.full_name}!</h2>

                <div style="background: #f8f9fa; padding: 1.5rem; border-radius: 10px; margin: 1.5rem 0; border-left: 4px solid #006a4e;">
                    <h3 style="margin-top: 0; color: #2c3e50;">{subject}</h3>
                    <p style="font-size: 1.1rem; color: #333; margin: 0;">{message}</p>
                </div>

                <div style="text-align: center; margin: 2rem 0;">
                    <a href="{url_for('league.view_league_details', league_id=get_league_id_by_name(league_name), _external=True) if get_league_id_by_name else '#'}"
                       style="background: #006a4e; color: white; padding: 1rem 2rem; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                        View League Details
                    </a>
                </div>

                <p style="color: #666; font-size: 0.9rem; text-align: center;">
                    Keep up the great work! Good luck in the rest of the tournament.
                </p>
            </div>

            <div style="background: #f8f9fa; padding: 1rem; text-align: center; color: #666; font-size: 0.8rem;">
                <p>© 2025 Fantasy Golf. All rights reserved.</p>
                <p style="margin: 0;">
                    <a href="#" style="color: #666; text-decoration: none;">Unsubscribe</a> |
                    <a href="#" style="color: #666; text-decoration: none;">Update Preferences</a>
                </p>
            </div>
        </div>
        """

        # Create plain text version
        text_body = f"""
        Hi {user.full_name}!

        {subject}
        {message}

        League: {league_name}

        Log in to your Fantasy Golf account to see the latest standings and track your progress.

        Good luck!

        The Fantasy Golf Team
        """

        # Send the email
        msg = Message(
            subject=f"Fantasy Golf: {subject}",
            recipients=[user.email],
            html=html_body,
            body=text_body
        )

        mail.send(msg)
        current_app.logger.info(f"Rank change email sent to {user.email}: {subject}")
        return True

    except Exception as e:
        current_app.logger.error(f"Failed to send rank change email to user {user_id}: {str(e)}")
        return False

def send_big_mover_email(user_id, new_rank, league_name):
    """Send email for big positive rank movement (5+ positions up)"""
    subject = "Big Mover! 📈"
    message = f"You've jumped up to P{new_rank} in '{league_name}'! Your players are performing excellently."
    return send_rank_change_email(user_id, subject, message, league_name)

def send_big_drop_email(user_id, new_rank, league_name):
    """Send email for big negative rank movement (5+ positions down)"""
    subject = "Position Update 📉"
    message = f"You've dropped to P{new_rank} in '{league_name}'. Don't worry - there's still time to climb back up!"
    return send_rank_change_email(user_id, subject, message, league_name)

def send_leader_email(user_id, league_name):
    """Send email when user moves into 1st place"""
    subject = "You're in the Lead! 🏆"
    message = f"Congratulations! You've moved into 1st place in '{league_name}'. Keep it up!"
    return send_rank_change_email(user_id, subject, message, league_name)

def send_leader_lost_email(user_id, new_rank, league_name):
    """Send email when user loses 1st place"""
    subject = "Leader Change 👑"
    message = f"You've been knocked out of 1st place in '{league_name}' and are now P{new_rank}. Time to fight back!"
    return send_rank_change_email(user_id, subject, message, league_name)

def get_league_id_by_name(league_name):
    """Helper function to get league ID by name for URL generation"""
    try:
        from .models import League
        league = League.query.filter_by(name=league_name).first()
        return league.id if league else None
    except:
        return None

