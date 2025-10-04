from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Message
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import re
from fantasy_league_app import db, mail, limiter
from fantasy_league_app.models import User, Club, League, SiteAdmin, LeagueEntry
from . import auth_bp, validators
from .decorators import redirect_if_authenticated, admin_required, user_required
from ..forms import (RegistrationForm, UserLoginForm, ClubLoginForm,
                     SiteAdminRegistrationForm, ClubRegistrationForm)
from ..utils import send_email_verification, send_email_verification_success, check_email_verification_required, validate_email_security, generate_verification_token, send_verification_email_graph

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
    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()

        # Enhanced email validation
        is_valid, error_message = validate_email_security(email)
        if not is_valid:
            current_app.logger.warning(f"Registration blocked - {error_message}: {email} from IP: {request.remote_addr}")
            flash('Please use a valid email address from a standard email provider.', 'danger')
            return redirect(url_for('auth.register'))

        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            # Log potential account enumeration attempt
            current_app.logger.warning(f"Registration attempt with existing email: {email} from IP: {request.remote_addr}")
            flash('An account with this email already exists.', 'danger')
            return redirect(url_for('auth.register'))

        # Create new user (email_verified defaults to False)
        user = User(
            full_name=form.full_name.data.strip(),
            email=email,
            password_hash=generate_password_hash(form.password.data),
        )

        db.session.add(user)
        db.session.commit()

        token = generate_verification_token(user.email)

        # Send verification email
        if send_verification_email_graph(user):
            flash('Account created! Please check your email to verify your account before logging in.', 'success')
        else:
            flash('Account created, but failed to send verification email. You can request a new one.', 'warning')

        return redirect(url_for('auth.email_verification_pending'))

    return render_template('auth/register.html', form=form)

@auth_bp.route('/register_club', methods=['GET', 'POST'])
@redirect_if_authenticated
def register_club():

    if current_user.is_authenticated:
        return redirect(url_for('main.club_dashboard'))

    # NOTE: You should create a specific ClubRegistrationForm in forms.py
    # For this example, I'll assume it has 'club_name', 'email', and 'password' fields.
    form = ClubRegistrationForm() # Replace with your actual club registration form

    if form.validate_on_submit():
        # Create a new club instance
        club = Club(
            club_name=form.club_name.data,
            email=form.email.data,
            contact_person=form.contact_person.data,
            phone_number=form.phone_number.data,
            website=form.website.data,
            address=form.address.data
            # Add other fields like contact_person, etc.
        )
        # Use the set_password method to create the secure hash
        club.set_password(form.password.data)

        db.session.add(club)
        db.session.commit()

        flash('Your club account has been created and is pending approval.', 'success')
        return redirect(url_for('auth.login_choice'))

    return render_template('auth/register_club.html', title='Club Registration', form=form)


@auth_bp.route('/register-site-admin', methods=['GET', 'POST'])
def register_site_admin():
    """
    Provides a registration page for the first site admin using the SiteAdmins table.
    This route is only accessible if no site admins exist.
    """
    # Check if a site admin already exists in the new SiteAdmin table
    if SiteAdmin.query.first():
        flash('A site admin account has already been registered.', 'warning')
        return redirect(url_for('main.index'))

    form = SiteAdminRegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        admin_user = SiteAdmin(
            username=form.username.data,
            password_hash=hashed_password
        )
        db.session.add(admin_user)
        db.session.commit()
        flash('Site admin account created successfully. Please log in.', 'success')
        # IMPORTANT: You will need to create this login route for admins
        return redirect(url_for('auth.login_site_admin'))

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
    league_code = request.args.get('code')
    return render_template('auth/login_choice.html', title='Login', league_code=league_code)


@auth_bp.route('/login/user', methods=['POST'])
def login_user_account():
    if current_user.is_authenticated:
        return redirect(url_for('main.user_dashboard'))

    # Use the form to validate the request
    form = UserLoginForm()

    # This block will only run if the form is submitted and valid
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.check_password(form.password.data):
           # Check if email is verified
            if not user.email_verified:
                flash('Please verify your email address before logging in.', 'warning')
                return redirect(url_for('auth.email_verification_pending'))

            # Check if account is active
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'danger')
                return redirect(url_for('auth.login_choice'))

            # LOGIN WITH REMEMBER ME
            login_user(user, remember=form.remember_me.data)  # USE THE FORM FIELD

            # Check if the user was trying to join a league
            league_code = form.league_code.data
            if league_code:
                league = League.query.filter_by(league_code=league_code).first()
                if league:
                    flash('Login successful! You can now join the league.', 'success')
                    return redirect(url_for('league.add_entry', league_id=league.id))

            flash('Logged in successfully!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.user_dashboard'))
        else:
            flash('Login unsuccessful. Please check your email and password.', 'danger')

    # If the form is not valid or login fails, redirect back to the choice page
    return redirect(url_for('auth.login_choice'))

@auth_bp.route('/login/club', methods=['POST'])
def login_club_account():
    """Handles the club login form submission."""
    if current_user.is_authenticated:
        return redirect(url_for('main.club_dashboard'))

    # Use the ClubLoginForm to process and validate the incoming data
    form = ClubLoginForm()

    # validate_on_submit() checks if it's a POST request and if the data is valid
    if form.validate_on_submit():
        # Find the club by the email provided in the form
        club = Club.query.filter_by(email=form.email.data.lower().strip()).first()

        # Check if the club exists and the password is correct
        if club and club.check_password(form.password.data):
            # Check if account is active
            if not club.is_active:
                flash('Your club account has been deactivated. Please contact support.', 'danger')
                return redirect(url_for('auth.login_choice'))

            # LOGIN WITH REMEMBER ME
            login_user(club, remember=form.remember_me.data)  # USE THE FORM FIELD
            flash(f'Welcome back, {club.club_name}!', 'success')

            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.club_dashboard'))
        else:
            flash('Login unsuccessful. Please check your email and password.', 'danger')
            # Redirect back to the login page with the form visible
            return redirect(url_for('auth.login_choice'))

    # If form validation fails, redirect back to the login page
    # Flask-WTF will automatically flash error messages for failed validations
    return redirect(url_for('auth.login_choice'))



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
        remember = request.form.get('remember_me', False)

        admin, error = _authenticate_and_login(SiteAdmin, 'username', username, password)

        if error:
            flash(error, 'danger')
            return redirect(url_for('auth.login_site_admin'))

        login_user(admin, remember=bool(remember))

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


##########
##Email Verification##

@auth_bp.route('/verify-email/<token>')
@limiter.limit("10 per hour")
def verify_email(token):
    """Verify email address using token with enhanced security logging"""

    # Log verification attempt
    current_app.logger.info(f"Email verification attempted with token: {token[:10]}... from IP: {request.remote_addr}")

    # Find user with this token
    user = User.verify_email_token(token)

    if not user:
        # Log failed verification attempt with more details
        current_app.logger.warning(
            f"Invalid verification token used: {token[:10]}... "
            f"from IP: {request.remote_addr} "
            f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}"
        )
        flash('Invalid or expired verification link. Please request a new one.', 'danger')
        return redirect(url_for('auth.resend_verification'))

    if user.email_verified:
        current_app.logger.info(f"Already verified email attempted verification: {user.email} from IP: {request.remote_addr}")
        flash('Your email has already been verified. You can log in now.', 'info')
        return redirect(url_for('auth.login_choice'))

    # Log successful verification
    current_app.logger.info(f"Email successfully verified for user: {user.email} from IP: {request.remote_addr}")

    # Verify the email
    user.verify_email()

    # Send welcome email
    send_email_verification_success(user)

    flash('Email verified successfully! You can now log in to your account.', 'success')
    return redirect(url_for('auth.login_choice'))

@auth_bp.route('/resend-verification', methods=['GET', 'POST'])
# @limiter.limit("5 per hour")
def resend_verification():
    """Resend email verification"""

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        if not email:
            flash('Please enter your email address.', 'danger')
            return redirect(url_for('auth.resend_verification'))

        user = User.query.filter_by(email=email).first()

        if not user:
            # Don't reveal if email exists or not for security
            flash('If an account with that email exists, a verification email has been sent.', 'info')
            return redirect(url_for('auth.resend_verification'))

        if user.email_verified:
            flash('This email address is already verified. You can log in now.', 'info')
            return redirect(url_for('auth.login_choice'))

        token = generate_verification_token(email)

        if send_verification_email_graph(user.email, token):
            flash('Verification email sent! Please check your inbox.', 'success')
        else:
            flash('Failed to send verification email. Please try again later.', 'danger')

        return redirect(url_for('auth.resend_verification'))

    return render_template('auth/resend_verification.html')

@auth_bp.route('/email-verification-pending')
def email_verification_pending():
    """Show email verification pending page"""
    return render_template('auth/email_verification_pending.html')