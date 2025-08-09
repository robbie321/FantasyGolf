from functools import wraps
from flask import redirect, url_for
from flask_login import current_user

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