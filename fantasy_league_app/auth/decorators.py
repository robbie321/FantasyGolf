from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user
from ..models import SiteAdmin, User, Club

def redirect_if_authenticated(f):
    """Redirects a user to their dashboard if they are already authenticated."""
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if current_user.is_authenticated:
            if getattr(current_user, 'is_site_admin', False):
                return redirect(url_for('admin.admin_dashboard'))
            elif getattr(current_user, 'is_club_admin', False):
                return redirect(url_for('main.club_dashboard'))
            else:
                return redirect(url_for('main.user_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print(f"\n--- DEBUG: @user_required decorator is checking access ---")
        print(f"DEBUG: current_user object is: {current_user}")
        print(f"DEBUG: Type of current_user is: {type(current_user)}")
        print(f"DEBUG: Is authenticated: {current_user.is_authenticated}")
        print(f"DEBUG: Is instance of User: {isinstance(current_user, User)}")
        print(f"DEBUG: Is instance of Club: {isinstance(current_user, Club)}")
        # We need to ensure the user is logged in AND is an instance of User or Club.
        if not current_user.is_authenticated or not (isinstance(current_user, User) or isinstance(current_user, Club)):
            flash("You must be logged in as a player or a club to access this page.", "warning")
            return redirect(url_for('auth.login_choice'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not isinstance(current_user, SiteAdmin):
            flash("You must be an administrator to access this page.", "danger")
            return redirect(url_for('auth.login_site_admin'))
        return f(*args, **kwargs)
    return decorated_function