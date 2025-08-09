# fantasy_league_app/auth/validators.py
import re
from fantasy_league_app.models import User, Club, SiteAdmin



def validate_club_registration(form_data):
    """Validates the entire club registration form."""
    errors = []
    club_name = form_data.get('club_name', '').strip()
    email = form_data.get('email', '').strip()
    password = form_data.get('password', '')
    confirm_password = form_data.get('confirm_password', '')

    if 'terms' not in form_data:
        errors.append('You must accept the Terms & Conditions.')

    if error := validate_club_name(club_name): errors.append(error)
    elif Club.query.filter_by(club_name=club_name).first():
        errors.append('A club with this name is already registered.')

    if error := validate_email_format(email): errors.append(error)
    elif Club.query.filter_by(email=email).first() or User.query.filter_by(email=email).first():
        errors.append('Email already registered by a club or user.')

    if error := validate_contact_person(form_data.get('contact_person', '')): errors.append(error)
    if error := validate_phone_number(form_data.get('phone_number', '')): errors.append(error)
    if error := validate_address(form_data.get('address', '')): errors.append(error)

    if password != confirm_password:
        errors.append('Passwords do not match.')

    if error := validate_password_strength(password): errors.append(error)
    elif is_common_password(password):
        errors.append('This password is too common. Please choose a stronger one.')

    return errors

def validate_user_registration(form_data):
    """Validates the entire user registration form."""
    errors = []
    full_name = form_data.get('full_name', '').strip()
    email = form_data.get('email', '').strip()
    password = form_data.get('password', '')
    confirm_password = form_data.get('confirm_password', '')

    if 'terms' not in form_data:
        errors.append('You must accept the Terms & Conditions.')

    if error := validate_full_name(full_name): errors.append(error)

    if error := validate_email_format(email): errors.append(error)
    elif User.query.filter_by(email=email).first() or Club.query.filter_by(email=email).first():
        errors.append('Email already registered. Please use a different email or log in.')

    if password != confirm_password:
        errors.append('Passwords do not match.')

    if error := validate_password_strength(password): errors.append(error)
    elif is_common_password(password):
        errors.append('This password is too common. Please choose a stronger one.')

    return errors


# --- Helper Functions for Validation ---

def validate_full_name(name):
    """Validates full name: max 100 chars, letters, spaces, apostrophes."""
    if not name:
        return "Full name cannot be empty."
    if len(name) > 100:
        return "Full name cannot exceed 100 characters."
    if not re.fullmatch(r"^[a-zA-Z\s']+$", name):
        return "Full name can only contain letters, spaces, and apostrophes (')."
    return None

def validate_email_format(email):
    """Validates email format: letters, @, and . (simplified)."""
    if not email:
        return "Email address cannot be empty."
    # Simplified regex as requested: allows letters, numbers, dots before @, and letters, numbers, dots after @
    if not re.fullmatch(r"^[a-zA-Z0-9.]+@[a-zA-Z0-9.]+$", email):
        return "Email address format is invalid. Only letters, numbers, '@', and '.' are allowed."
    return None

def validate_password_strength(password):
    """Validates password strength: min 8 chars, 1 uppercase, 1 special, 1 number."""
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(char.isupper() for char in password):
        return "Password must contain at least one uppercase letter."
    if not any(char.isdigit() for char in password):
        return "Password must contain at least one number."
    special_characters = r"!@#$%^&*()-_+=[]{}|\;:,.<>/?`~"
    if not any(char in special_characters for char in password):
        return "Password must contain at least one special character."
    return None

def is_common_password(password):
    """Checks against a small list of common passwords (placeholder)."""
    common_passwords = ['password', '123456', 'qwerty', 'admin', 'user123'] # Add more as needed
    return password.lower() in common_passwords

def validate_club_name(name):
    """Validates club name: letters, spaces, apostrophes."""
    if not name:
        return "Club name cannot be empty."
    if not re.fullmatch(r"^[a-zA-Z0-9\s']+$", name): # Allowing numbers for club names like "Golf Club 18"
        return "Club name can only contain letters, numbers, spaces, and apostrophes (')."
    return None

def validate_contact_person(contact_person):
    """Validates contact person name: letters, spaces, apostrophes."""
    if not contact_person:
        return "Contact person name cannot be empty."
    if not re.fullmatch(r"^[a-zA-Z\s.'-]+$", contact_person): # Allowing hyphens and periods for names
        return "Contact person name can only contain letters, spaces, apostrophes, hyphens, and periods."
    return None

def validate_phone_number(phone):
    """Validates Irish mobile or landline: +353 followed by 9-10 digits."""
    if not phone:
        return "Phone number cannot be empty."
    # Regex for +353 followed by 9 or 10 digits
    if not re.fullmatch(r"^\+353[0-9]{9,10}$", phone):
        return "Phone number must be an Irish number, starting with +353 and followed by 9 or 10 digits."
    return None

def validate_address(address):
    """Validates address: alphanumeric, spaces, commas, hyphens, periods, apostrophes."""
    if not address:
        return "Address cannot be empty."
    # Allowing common address characters
    if not re.fullmatch(r"^[a-zA-Z0-9\s,.\-']+$", address):
        return "Address can only contain letters, numbers, spaces, commas, periods, hyphens, and apostrophes."
    return None

def validate_username(username):
    """Validates username for SiteAdmin."""
    if not username:
        return "Username cannot be empty."
    if len(username) < 3:
        return "Username must be at least 3 characters long."
    if not re.fullmatch(r"^[a-zA-Z0-9_.]+$", username):
        return "Username can only contain letters, numbers, underscores, and periods."
    return None

def validate_full_name(name):
    if not name: return "Full name cannot be empty."
    if len(name) > 100: return "Full name cannot exceed 100 characters."
    if not re.fullmatch(r"^[a-zA-Z\s']+$", name): return "Full name can only contain letters, spaces, and apostrophes (')."
    return None