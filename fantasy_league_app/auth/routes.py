from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Message
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import re
from fantasy_league_app import db, mail
from fantasy_league_app.models import User, Club, SiteAdmin, LeagueEntry
from . import auth_bp, validators
from .decorators import redirect_if_authenticated
from ..forms import (RegistrationForm, LoginForm,
                     SiteAdminRegistrationForm)

# Helper function to create the serializer
def get_serializer(secret_key):
    return URLSafeTimedSerializer(secret_key)

# Helper function to send the email
def send_reset_email(user):
    s = get_serializer(current_app.config['SECRET_KEY'])
    token = s.dumps(user.email, salt='password-reset-salt')

    msg = Message('Password Reset Request',
                  sender=current_app.config['MAIL_DEFAULT_SENDER'],
                  recipients=[user.email])

    reset_url = url_for('auth.reset_token', token=token, _external=True)
    msg.body = f'''To reset your password, visit the following link:{reset_url}

    If you did not make this request then simply ignore this email and no changes will be made.
    '''
    mail.send(msg)


def _authenticate_and_login(user_model, identifier_field, identifier, password):
    """
    Authenticates a user from a given model and returns the user object or an error message.
    """
    user = user_model.query.filter(getattr(user_model, identifier_field) == identifier).first()

    if not user:
        return None, f"No account found with that {identifier_field}. Please check and try again."

    # SiteAdmin does not have an 'is_active' field, so we check for it
    if hasattr(user, 'is_active') and not user.is_active:
        return None, "This account has been deactivated. Please contact the site administrator."

    if not check_password_hash(user.password_hash, password):
        return None, "Incorrect password. Please try again."

    login_user(user, remember=True)
    return user, None



# Renamed login_user from Flask-Login to avoid potential conflicts if a model also has a login_user method
from flask_login import login_user as flask_login_user

@auth_bp.route('/register', methods=['GET', 'POST'])
@redirect_if_authenticated
def register():
    if request.method == 'POST':
        errors = validators.validate_user_registration(request.form)
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('auth/register.html', form=request.form)

        full_name = request.form['full_name'].strip()
        email = request.form['email'].strip()
        password = request.form['password']

        hashed_password = generate_password_hash(password)
        new_user = User(full_name=full_name, email=email, password_hash=hashed_password)

        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('auth.login_choice'))
        except Exception as e:
            db.session.rollback()
            flash(f'Registration failed: {e}', 'danger')

    return render_template('auth/register.html')

@auth_bp.route('/register_club', methods=['GET', 'POST'])
@redirect_if_authenticated
def register_club():

    if request.method == 'POST':
        errors = validators.validate_club_registration(request.form)
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('auth/register_club.html', form=request.form)

        hashed_password = generate_password_hash(request.form['password'])
        new_club = Club(
            club_name=request.form['club_name'].strip(),
            contact_person=request.form['contact_person'].strip(),
            email=request.form['email'].strip(),
            phone_number=request.form['phone_number'].strip(),
            website=request.form['website'].strip(),
            address=request.form['address'].strip(),
            password_hash=hashed_password
        )
        try:
            db.session.add(new_club)
            db.session.commit()
            flash('Club registration successful! Please log in.', 'success')
            return redirect(url_for('auth.login_choice'))
        except Exception as e:
            db.session.rollback()
            flash(f'Club registration failed: {e}', 'danger')

    return render_template('auth/register_club.html')
@auth.route('/register-site-admin', methods=['GET', 'POST'])
def register_site_admin():
    """
    Provides a registration page for the first site admin.
    This route is only accessible if no other site admins exist.
    """
    # Check if a site admin already exists in the database
    if User.query.filter_by(is_site_admin=True).first():
        flash('A site admin account has already been registered.', 'warning')
        return redirect(url_for('main.index'))

    form = SiteAdminRegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        admin_user = User(
            full_name=form.full_name.data,
            email=form.email.data,
            password_hash=hashed_password,
            is_site_admin=True,
            is_active=True  # Activate the admin account immediately
        )
        db.session.add(admin_user)
        db.session.commit()
        flash('Site admin account created successfully. Please log in.', 'success')
        return redirect(url_for('auth.user_login'))

    return render_template('auth/register_site_admin.html', title='Register Site Admin', form=form)

@auth_bp.route('/login_choice', methods=['GET'])
def login_choice():
    if current_user.is_authenticated:
        if getattr(current_user, 'is_site_admin', False):
            return redirect(url_for('admin.admin_dashboard'))
        elif getattr(current_user, 'is_club_admin', False):
            return redirect(url_for('main.club_dashboard'))
        else:
            return redirect(url_for('main.user_dashboard'))
    return render_template('auth/login_choice.html')


@auth_bp.route('/login/user', methods=['POST'])
def login_user_account():
    if current_user.is_authenticated:
        return redirect(url_for('main.user_dashboard'))

    email = request.form['email'].strip()
    password = request.form['password']

    user, error = _authenticate_and_login(User, 'email', email, password)

    if error:
        flash(error, 'danger')
        return redirect(url_for('auth.login_choice'))

    flash('Logged in successfully as user!', 'success')
    next_page = request.args.get('next')
    return redirect(next_page or url_for('main.user_dashboard'))

@auth_bp.route('/login/club', methods=['POST'])
def login_club_account():
    if current_user.is_authenticated:
        return redirect(url_for('main.club_dashboard'))

    email = request.form['email'].strip()
    password = request.form['password']

    club, error = _authenticate_and_login(Club, 'email', email, password)

    if error:
        flash(error, 'danger')
        return redirect(url_for('auth.login_choice'))

    flash('Logged in successfully as club admin!', 'success')
    next_page = request.args.get('next')
    return redirect(next_page or url_for('main.club_dashboard'))



@auth_bp.route('/force-change-password', methods=['GET', 'POST'])
@login_required
def force_change_password():
    # If the user doesn't need a reset, send them to their dashboard
    if not getattr(current_user, 'password_reset_required', False):
        if getattr(current_user, 'is_club_admin', False):
            return redirect(url_for('main.club_dashboard'))
        else:
            return redirect(url_for('main.user_dashboard'))

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash('Passwords do not match. Please try again.', 'danger')
            return redirect(url_for('auth.force_change_password'))

        # Here you could add password strength validation if desired

        # Hash the new password and update the user/club
        current_user.password_hash = generate_password_hash(new_password)
        current_user.password_reset_required = False
        db.session.commit()

        flash('Your password has been updated successfully. Please log in again.', 'success')
        return redirect(url_for('auth.logout'))

    return render_template('auth/force_change_password.html')



@auth_bp.route('/login_site_admin', methods=['GET', 'POST'])
@redirect_if_authenticated
def login_site_admin():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        admin, error = _authenticate_and_login(SiteAdmin, 'username', username, password)

        if error:
            flash(error, 'danger')
            return redirect(url_for('auth.login_site_admin'))

        flash('Logged in successfully as Site Admin!', 'success')
        next_page = request.args.get('next')
        return redirect(next_page or url_for('admin.admin_dashboard'))

    return render_template('auth/login_site_admin.html')


# Add this new route at the end of the file, before the final logout route.

@auth_bp.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    """Deletes a user and all their associated league entries."""
    # Ensure the user is a regular user, not a club or admin
    if not isinstance(current_user, User):
        flash('This function is only available for user accounts.', 'danger')
        return redirect(url_for('main.index'))

    try:
        # Step 1: Delete all league entries associated with this user
        LeagueEntry.query.filter_by(user_id=current_user.id).delete()

        # Step 2: Delete the user object itself
        db.session.delete(current_user)

        # Step 3: Commit the changes to the database
        db.session.commit()

        # Step 4: Log the user out
        logout_user()

        flash('Your account and all associated data have been permanently deleted.', 'success')
        return redirect(url_for('main.index'))

    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred while deleting your account: {e}', 'danger')
        return redirect(url_for('main.user_dashboard'))

# You also need to import the 'User' and 'LeagueEntry' models if they aren't already available
# Make sure these imports are at the top of your auth/routes.py file:
from fantasy_league_app.models import User, Club, SiteAdmin, LeagueEntry
from flask_login import login_user, logout_user, login_required, current_user


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    session.pop('simulated_payment_confirmed', None)
    return redirect(url_for('main.index'))



# --- NEW: Password Reset Request Routes ---

@auth_bp.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            send_reset_email(user)
            flash('An email has been sent with instructions to reset your password.', 'info')
            return redirect(url_for('auth.login_choice'))
        else:
            flash('No account found with that email address.', 'warning')

    return render_template('auth/request_password_reset.html')


@auth_bp.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    s = get_serializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=1800) # Token expires in 30 minutes
    except (SignatureExpired, BadTimeSignature):
        flash('That is an invalid or expired token.', 'warning')
        return redirect(url_for('auth.reset_request'))

    user = User.query.filter_by(email=email).first()
    if user is None:
        flash('Invalid token.', 'warning')
        return redirect(url_for('auth.reset_request'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.reset_token', token=token))

        user.password_hash = generate_password_hash(password)
        db.session.commit()
        flash('Your password has been updated! You are now able to log in.', 'success')
        return redirect(url_for('auth.login_choice'))

    return render_template('auth/reset_password.html', token=token)