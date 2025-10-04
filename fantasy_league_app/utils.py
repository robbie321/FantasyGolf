import json
import msal
import requests
from fantasy_league_app import db, mail
from fantasy_league_app.models import Player
from datetime import datetime, timedelta
from functools import wraps
from flask import redirect, url_for, request, current_app
from flask_mail import Message
from flask_login import current_user
from pywebpush import webpush, WebPushException
from .models import PushSubscription
from itsdangerous import URLSafeTimedSerializer

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



def send_push_notification(user_id, title, body, icon=None, url=None):
    """
    Enhanced push notification function that uses the new service
    Maintains backward compatibility with your existing code
    """
    try:
        from fantasy_league_app.push.services import push_service

        result = push_service.send_notification_sync(
            user_ids=[user_id],
            notification_type='general',
            title=title,
            body=body,
            icon=icon,
            url=url
        )

        return result.get('success', 0) > 0

    except Exception as e:
        current_app.logger.error(f"Push notification failed: {e}")
        return False

def send_league_notification(league_id, title, body, notification_type='league_update'):
    """Send notification to all users in a league"""
    try:
        from fantasy_league_app.push.services import send_league_update_notification
        send_league_update_notification(league_id, body)
        return True
    except Exception as e:
        current_app.logger.error(f"League notification failed: {e}")
        return False


def send_prize_notification(user_id, prize_amount, league_name):
    """Send prize won notification to user"""
    try:
        from fantasy_league_app.push.services import send_prize_won_notification
        send_prize_won_notification(user_id, prize_amount, league_name)
        return True
    except Exception as e:
        current_app.logger.error(f"Prize notification failed: {e}")
        return False



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


def send_email_via_graph(to_email, subject, body):
    """Send email using Microsoft Graph API"""

    # Get config
    client_id = current_app.config.get('AZURE_CLIENT_ID')
    client_secret = current_app.config.get('AZURE_CLIENT_SECRET')
    tenant_id = current_app.config.get('AZURE_TENANT_ID')
    sender_email = current_app.config.get('MAIL_USERNAME')

    # Get access token
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret
    )

    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

    if "access_token" not in result:
        raise Exception(f"Could not get access token: {result.get('error_description')}")

    # Send email via Graph API
    headers = {
        'Authorization': f'Bearer {result["access_token"]}',
        'Content-Type': 'application/json'
    }

    email_data = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email
                    }
                }
            ]
        },
        "saveToSentItems": "true"
    }

    response = requests.post(
        f'https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail',
        headers=headers,
        json=email_data
    )

    if response.status_code != 202:
        raise Exception(f"Failed to send email: {response.text}")

    return True


def send_verification_email_graph(user_email, token):
    """Send verification email using Microsoft Graph API"""
    try:
        from flask import current_app, url_for

        # Get Azure config
        client_id = current_app.config.get('AZURE_CLIENT_ID')
        client_secret = current_app.config.get('AZURE_CLIENT_SECRET')
        tenant_id = current_app.config.get('AZURE_TENANT_ID')
        sender_email = current_app.config.get('MAIL_USERNAME')

        if not all([client_id, client_secret, tenant_id, sender_email]):
            current_app.logger.error("Missing Azure configuration")
            return False

        # Get access token
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id,
            authority=authority,
            client_credential=client_secret
        )

        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

        if "access_token" not in result:
            current_app.logger.error(f"Failed to get access token: {result.get('error_description')}")
            return False

        # Build verification URL
        verification_url = url_for('auth.verify_email', token=token, _external=True)

        # Email content
        subject = "Verify Your Fantasy Fairways Account"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #006a4e;">Welcome to Fantasy Fairways!</h2>
                <p>Thank you for registering. Please verify your email address to complete your registration.</p>
                <p style="margin: 30px 0;">
                    <a href="{verification_url}"
                       style="background-color: #006a4e; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; display: inline-block;">
                        Verify Email Address
                    </a>
                </p>
                <p style="color: #666; font-size: 14px;">
                    If the button doesn't work, copy and paste this link into your browser:
                </p>
                <p style="color: #006a4e; word-break: break-all; font-size: 14px;">
                    {verification_url}
                </p>
                <p style="color: #999; font-size: 12px; margin-top: 30px;">
                    This link will expire in 24 hours. If you didn't create an account, please ignore this email.
                </p>
            </div>
        </body>
        </html>
        """

        # Send email via Graph API
        headers = {
            'Authorization': f'Bearer {result["access_token"]}',
            'Content-Type': 'application/json'
        }

        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": body
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": user_email
                        }
                    }
                ]
            },
            "saveToSentItems": "true"
        }

        response = requests.post(
            f'https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail',
            headers=headers,
            json=email_data,
            timeout=10
        )

        if response.status_code == 202:
            current_app.logger.info(f"Verification email sent successfully to {user_email}")
            return True
        else:
            current_app.logger.error(f"Failed to send email: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        current_app.logger.error(f"Failed to send verification email to {user_email}: {e}")
        return False

def generate_verification_token(user_email):
    """Generate verification token"""
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(user_email, salt='email-verification')


def verify_token(token, expiration=86400):
    """Verify token (default 24 hours)"""
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt='email-verification', max_age=expiration)
        return email
    except:
        return None

####################################################
############### use graph above

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


def log_user_activity(user_id, activity_type, description, league_id=None, extra_data=None):
    """Log user activity for the activity feed"""
    from .models import UserActivity

    activity = UserActivity(
        user_id=user_id,
        activity_type=activity_type,
        description=description,
        league_id=league_id
    )

    # Set extra data if provided
    if extra_data:
        activity.set_extra_data(extra_data)

    db.session.add(activity)
    db.session.commit()

def get_recent_activity(user_id, limit=10):
    """Get recent user activity for the activity feed"""
    from .models import UserActivity

    activities = UserActivity.query.filter_by(user_id=user_id).order_by(
        UserActivity.created_at.desc()
    ).limit(limit).all()

    activity_list = []
    for activity in activities:
        activity_list.append({
            'type': activity.activity_type,
            'description': activity.description,
            'time_ago': get_time_ago(activity.created_at),
            'extra_data': activity.get_extra_data()
        })

    return activity_list

def update_user_achievements(user_id):
    """Check and update user achievements based on current stats"""
    from .models import User

    user = User.query.get(user_id)
    if not user:
        return

    # Get current achievements
    achievements = user.get_achievements()
    stats = calculate_user_stats(user_id)

    # Check each achievement
    achievement_updates = []

    # First Timer - Join first league
    if stats['leagues_played'] >= 1 and not achievements.get('first_timer'):
        achievements['first_timer'] = True
        achievement_updates.append('first_timer')

    # Victory Royale - Win first league
    if stats['leagues_won'] >= 1 and not achievements.get('victory_royale'):
        achievements['victory_royale'] = True
        achievement_updates.append('victory_royale')

    # Regular Player - Play 5 leagues
    if stats['leagues_played'] >= 5 and not achievements.get('regular_player'):
        achievements['regular_player'] = True
        achievement_updates.append('regular_player')

    # Triple Crown - Win 3 leagues
    if stats['leagues_won'] >= 3 and not achievements.get('triple_crown'):
        achievements['triple_crown'] = True
        achievement_updates.append('triple_crown')

    # Hot Streak - Win 3 in a row
    if stats['current_streak'] >= 3 and not achievements.get('hot_streak'):
        achievements['hot_streak'] = True
        achievement_updates.append('hot_streak')

    # Century Club - Earn €100
    if stats['total_winnings'] >= 100 and not achievements.get('century_club'):
        achievements['century_club'] = True
        achievement_updates.append('century_club')

    # Save updated achievements
    if achievement_updates:
        user.set_achievements(achievements)
        db.session.commit()

        # Send achievement notification emails
        for achievement in achievement_updates:
            send_achievement_email(user_id, achievement)

def send_achievement_email(user_id, achievement_name):
    """Send email notification for new achievement"""
    from .models import User

    user = User.query.get(user_id)
    if not user or not user.email:
        return

    achievement_data = {
        'first_timer': {
            'title': 'First Timer Achievement Unlocked!',
            'description': 'You\'ve joined your first league and started your fantasy golf journey!',
            'icon': '🎯'
        },
        'victory_royale': {
            'title': 'Victory Royale Achievement Unlocked!',
            'description': 'Congratulations on your first league victory!',
            'icon': '🏆'
        },
        'regular_player': {
            'title': 'Regular Player Achievement Unlocked!',
            'description': 'You\'ve played 5 leagues and are becoming a seasoned player!',
            'icon': '⭐'
        },
        'triple_crown': {
            'title': 'Triple Crown Achievement Unlocked!',
            'description': 'Amazing! You\'ve won 3 leagues - you\'re on fire!',
            'icon': '👑'
        },
        'hot_streak': {
            'title': 'Hot Streak Achievement Unlocked!',
            'description': 'Incredible! You\'ve won 3 leagues in a row!',
            'icon': '🔥'
        },
        'century_club': {
            'title': 'Century Club Achievement Unlocked!',
            'description': 'You\'ve earned over €100 in total winnings!',
            'icon': '💰'
        }
    }

    if achievement_name not in achievement_data:
        return

    achievement = achievement_data[achievement_name]

    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #ffd700, #ffed4e); padding: 2rem; text-align: center; border-radius: 15px 15px 0 0;">
            <div style="font-size: 4rem; margin-bottom: 1rem;">{achievement['icon']}</div>
            <h1 style="color: #2c3e50; margin: 0; font-size: 2rem;">Achievement Unlocked!</h1>
        </div>

        <div style="padding: 2rem; background: white; border-radius: 0 0 15px 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
            <h2 style="color: #006a4e; text-align: center; margin-bottom: 1rem;">{achievement['title']}</h2>

            <p style="font-size: 1.1rem; color: #333; text-align: center; line-height: 1.6;">
                {achievement['description']}
            </p>

            <div style="text-align: center; margin: 2rem 0;">
                <a href="{url_for('main.profile', _external=True)}"
                   style="background: #006a4e; color: white; padding: 1rem 2rem; text-decoration: none; border-radius: 25px; font-weight: bold; display: inline-block;">
                    View Your Profile
                </a>
            </div>

            <p style="color: #666; font-size: 0.9rem; text-align: center;">
                Keep playing to unlock more achievements and climb the leaderboards!
            </p>
        </div>
    </div>
    """

    try:
        msg = Message(
            subject=f"🏆 {achievement['title']}",
            recipients=[user.email],
            html=html_body
        )
        mail.send(msg)
        current_app.logger.info(f"Achievement email sent to {user.email}: {achievement_name}")

    except Exception as e:
        current_app.logger.error(f"Failed to send achievement email: {e}")

# Hook into existing functions to track activities
def track_league_join(user_id, league_id):
    """Track when user joins a league"""
    from .models import League

    league = League.query.get(league_id)
    if league:
        log_user_activity(
            user_id=user_id,
            activity_type='league_join',
            description=f"Joined '{league.name}'",
            league_id=league_id,
            extra_data={
                'league_name': league.name,
                'entry_fee': float(league.entry_fee) if league.entry_fee else 0
            }
        )

        # Update achievements
        update_user_achievements(user_id)


def track_league_win(user_id, league_id):
    """Track when user wins a league"""
    from .models import League

    league = League.query.get(league_id)
    if league:
        # Calculate winnings
        total_pot = len(league.entries) * league.entry_fee if league.entries else 0
        winnings = total_pot * 0.8  # Adjust based on your prize structure

        log_user_activity(
            user_id=user_id,
            activity_type='league_win',
            description=f"Won '{league.name}'!",
            league_id=league_id,
            extra_data={
                'league_name': league.name,
                'winnings': round(winnings, 2),
                'total_players': len(league.entries) if league.entries else 0
            }
        )

        # Update achievements
        update_user_achievements(user_id)


def calculate_user_stats(user_id):
    """Calculate comprehensive user statistics"""
    from .models import LeagueEntry, League

    # Get all user's league entries
    entries = LeagueEntry.query.filter_by(user_id=user_id).all()

    # Basic counts
    leagues_played = len(entries)
    leagues_won = len([e for e in entries if e.league.winner_id == user_id])

    # Calculate win percentage
    win_percentage = round((leagues_won / leagues_played * 100), 1) if leagues_played > 0 else 0

    # Calculate total winnings
    total_winnings = calculate_total_winnings(user_id)

    # Calculate current streak (consecutive wins)
    current_streak = calculate_current_streak(user_id)

    # Calculate days active (days since first league)
    days_active = calculate_days_active(user_id)

    # Calculate user level based on activities
    user_level = calculate_user_level(leagues_played, leagues_won, total_winnings)

    return {
        'leagues_played': leagues_played,
        'leagues_won': leagues_won,
        'win_percentage': win_percentage,
        'total_winnings': total_winnings,
        'current_streak': current_streak,
        'days_active': days_active,
        'user_level': user_level,
        'average_rank': calculate_average_rank(entries),
        'best_rank': calculate_best_rank(entries),
        'leagues_this_month': calculate_leagues_this_month(user_id)
    }

def calculate_total_winnings(user_id):
    """Calculate total prize money won by user"""
    from .models import League

    # Get all leagues won by this user
    won_leagues = League.query.filter_by(winner_id=user_id, is_finalized=True).all()

    total = 0
    for league in won_leagues:
        # Calculate prize based on your business logic
        if league.entries:
            total_pot = len(league.entries) * league.entry_fee
            # Assuming winner gets 80% of pot (adjust based on your model)
            prize = total_pot * 0.8
            total += prize

    return round(total, 2)

def calculate_current_streak(user_id):
    """Calculate current consecutive wins streak"""
    from .models import League, LeagueEntry

    # Get user's recent finalized leagues ordered by date
    recent_leagues = db.session.query(League).join(LeagueEntry).filter(
        LeagueEntry.user_id == user_id,
        League.is_finalized == True
    ).order_by(desc(League.end_date)).limit(20).all()

    streak = 0
    for league in recent_leagues:
        if league.winner_id == user_id:
            streak += 1
        else:
            break  # Streak broken

    return streak

def calculate_days_active(user_id):
    """Calculate days since user first joined a league"""
    from .models import LeagueEntry

    first_entry = LeagueEntry.query.filter_by(user_id=user_id).order_by(LeagueEntry.id).first()
    if not first_entry:
        return 0

    # Use the created_at field or league start_date as fallback
    first_date = getattr(first_entry, 'created_at', first_entry.league.start_date)
    if first_date:
        days_active = (datetime.utcnow() - first_date).days
        return max(0, days_active)
    return 0

def calculate_user_level(leagues_played, leagues_won, total_winnings):
    """Calculate user level based on activity and performance"""

    # Simple leveling system - adjust as needed
    points = 0
    points += leagues_played * 10  # 10 points per league
    points += leagues_won * 50     # 50 bonus points per win
    points += int(total_winnings)  # 1 point per euro won

    # Level thresholds
    if points < 50:
        return 1
    elif points < 150:
        return 2
    elif points < 300:
        return 3
    elif points < 500:
        return 4
    elif points < 750:
        return 5
    else:
        return min(10, 5 + (points - 750) // 200)  # Cap at level 10

def calculate_average_rank(entries):
    """Calculate user's average finishing position"""
    if not entries:
        return 0

    total_rank = 0
    finalized_count = 0

    for entry in entries:
        if entry.league.is_finalized and hasattr(entry, 'final_rank') and entry.final_rank:
            total_rank += entry.final_rank
            finalized_count += 1

    return round(total_rank / finalized_count, 1) if finalized_count > 0 else 0

def calculate_best_rank(entries):
    """Find user's best (lowest) finishing position"""
    best = float('inf')

    for entry in entries:
        if entry.league.is_finalized and hasattr(entry, 'final_rank') and entry.final_rank:
            if entry.final_rank < best:
                best = entry.final_rank

    return best if best != float('inf') else 0

def calculate_leagues_this_month(user_id):
    """Count leagues played this month"""
    from .models import LeagueEntry, League

    start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    count = db.session.query(LeagueEntry).join(League).filter(
        LeagueEntry.user_id == user_id,
        League.start_date >= start_of_month
    ).count()

    return count

def get_enhanced_league_history(user_id, limit=20):
    """Get detailed league history for the user"""
    from .models import LeagueEntry, League

    entries = db.session.query(LeagueEntry).join(League).filter(
        LeagueEntry.user_id == user_id
    ).order_by(desc(League.end_date)).limit(limit).all()

    history = []
    for entry in entries:
        league = entry.league

        # Use stored final_rank if available, otherwise calculate
        rank = getattr(entry, 'final_rank', None) or calculate_entry_rank(entry)

        # Calculate winnings for this league
        winnings = 0
        if league.winner_id == user_id and league.is_finalized:
            total_pot = len(league.entries) * league.entry_fee
            winnings = total_pot * 0.8  # Adjust based on your prize structure

        # Count total players
        total_players = len(league.entries)

        history.append({
            'league_id': league.id,
            'league_name': league.name,
            'rank': rank,
            'total_players': total_players,
            'winnings': round(winnings, 2),
            'is_winner': league.winner_id == user_id,
            'date_finished': league.end_date.strftime('%Y-%m-%d') if league.is_finalized else None,
            'is_active': not league.is_finalized
        })

    return history

def calculate_entry_rank(entry):
    """Calculate the rank of a specific entry in its league"""
    # Get all entries in the same league
    all_entries = entry.league.entries

    # Sort by total score (assuming lower score is better)
    sorted_entries = sorted(all_entries, key=lambda e: e.total_score or float('inf'))

    # Find the rank (1-indexed)
    for rank, e in enumerate(sorted_entries, 1):
        if e.id == entry.id:
            return rank

    return None

def get_recent_activity(user_id, limit=10):
    """Get recent user activity for the activity feed"""
    from .models import UserActivity

    # Try to get activities from UserActivity model first
    try:
        activities = UserActivity.query.filter_by(user_id=user_id).order_by(
            desc(UserActivity.created_at)
        ).limit(limit).all()

        activity_list = []
        for activity in activities:
            activity_list.append({
                'type': activity.activity_type,
                'description': activity.description,
                'time_ago': get_time_ago(activity.created_at),
                'extra_data': activity.get_extra_data() if hasattr(activity, 'get_extra_data') else {}
            })

        if activity_list:
            return activity_list

    except Exception as e:
        # If UserActivity table doesn't exist yet, fall back to generating from league data
        current_app.logger.warning(f"UserActivity table not available: {e}")

    # Fallback: Generate activity from league entries
    from .models import LeagueEntry, League

    recent_entries = db.session.query(LeagueEntry).join(League).filter(
        LeagueEntry.user_id == user_id
    ).order_by(desc(LeagueEntry.id)).limit(limit).all()

    activities = []
    for entry in recent_entries:
        league = entry.league

        # League join activity
        activities.append({
            'type': 'league_join',
            'description': f"Joined '{league.name}'",
            'time_ago': get_time_ago(getattr(entry, 'created_at', league.start_date)),
        })

        # League win activity (if won and finalized)
        if league.winner_id == user_id and league.is_finalized:
            activities.append({
                'type': 'league_win',
                'description': f"Won '{league.name}'!",
                'time_ago': get_time_ago(league.end_date),
            })

    # Sort by most recent and limit
    return activities[:limit]

def get_time_ago(date_time):
    """Convert datetime to human-readable time ago string"""
    if not date_time:
        return "Unknown"

    now = datetime.utcnow()
    diff = now - date_time

    if diff.days > 30:
        return f"{diff.days // 30} month{'s' if diff.days // 30 != 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    else:
        return "Just now"

