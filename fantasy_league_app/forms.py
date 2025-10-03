from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField, TextAreaField, IntegerField, HiddenField, DateField, DecimalField
from wtforms.validators import DataRequired, NumberRange, Email, EqualTo, ValidationError, Length, Optional
from .models import User, SiteAdmin

# Base form for both users and clubs
class CreateLeagueBaseForm(FlaskForm):
    name = StringField('League Name', validators=[DataRequired()])
    entry_fee = IntegerField('Entry Fee (€)', validators=[DataRequired(), NumberRange(min=0)])
    max_entries = IntegerField('Max Entries', validators=[DataRequired(), NumberRange(min=2)])
    player_bucket_id = SelectField('Player Bucket', coerce=int, validators=[DataRequired()])
    prize_pool_percentage = IntegerField('Creator Prize Share (%)', default=10, validators=[DataRequired(), NumberRange(min=0, max=50)])
    no_favorites = BooleanField('No Favorites Rule')
    tie_breaker_question = StringField('Tie Breaker Question', validators=[DataRequired()])
    submit = SubmitField('Create League')

# Specific form for regular users
class CreateUserLeagueForm(CreateLeagueBaseForm):
    pass # Inherits everything from the base form

# Specific form for clubs, with the custom prize option
class CreateClubLeagueForm(CreateLeagueBaseForm):
    custom_prizes_enabled = BooleanField('Enable Custom Prizes (e.g., Vouchers)')
    custom_prizes_text = TextAreaField('Custom Prize Details', validators=[Optional()])

class LeagueForm(FlaskForm):
    """
    A unified form for creating and editing leagues for both
    club and site admins.
    """
    name = StringField('League Name', validators=[DataRequired()])
    tour = SelectField('Select Tour', choices=[
        ('pga', 'PGA Tour'),
        ('euro', 'DP World Tour')
    ], validators=[DataRequired()])
    # start_date = DateField('Tournament Start Date', format='%Y-%m-%d', validators=[DataRequired()])
    player_bucket_id = SelectField('Player Pool', coerce=int, validators=[DataRequired()])
    entry_fee = DecimalField('Entry Fee (€)', places=2, validators=[DataRequired(), NumberRange(min=0)])
    prize_amount = IntegerField(
        'Prize Payout (%)',
        validators=[DataRequired(), NumberRange(min=10, max=100)],
        description="Percentage of the creator's 70% revenue share to be paid out."
    )
    max_entries = IntegerField('Max Entries', validators=[DataRequired(), NumberRange(min=1)])
    odds_limit = IntegerField('Minimum Combined Odds', validators=[DataRequired(), NumberRange(min=0)])
    prize_details = TextAreaField('Prize Details')
    rules = TextAreaField('Rules')
    # tie_breaker_question = StringField('Tie-Breaker Question', validators=[DataRequired()])
    no_favorites_rule = BooleanField("Enforce 'No Favorites' Rule")
    submit = SubmitField('Create League')

class EditLeagueForm(FlaskForm):
    """Form for club admins to edit an upcoming league."""
    name = StringField('League Name', validators=[DataRequired(), Length(min=2, max=100)])
    entry_fee = DecimalField('Entry Fee (€)', validators=[DataRequired(), NumberRange(min=0)])
    prize_details = StringField('Prize Details', validators=[Length(max=200)])
    rules = TextAreaField('Custom Rules')
    submit = SubmitField('Save Changes')

class PlayerBucketForm(FlaskForm):
    name = StringField('Bucket Name', validators=[DataRequired(), Length(min=3, max=150)])
    description = TextAreaField('Description', validators=[Length(max=300)])

    tour = SelectField('Tour', choices=[
        ('pga', 'PGA Tour'),
        ('euro', 'DP World Tour'),
    ], validators=[DataRequired()])

    submit = SubmitField('Create Bucket')

class UserLoginForm(FlaskForm):
    """Form for users to log in."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    league_code = StringField('League Code') # Hidden field to carry the code
    submit = SubmitField('Sign In')

class ClubLoginForm(FlaskForm):
    """Form for users to log in."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    league_code = StringField('League Code') # Hidden field to carry the code
    submit = SubmitField('Sign In')


class RegistrationForm(FlaskForm):
    """Form for new users to register."""
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match.')]
    )
    submit = SubmitField('Sign Up')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is already in use. Please choose a different one.')

class ClubRegistrationForm(FlaskForm):
    """Form for new clubs to register."""
    club_name = StringField('Club Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match.')]
    )
    contact_person=StringField('Contact Person', validators=[DataRequired(), Length(min=5, max=100)])
    phone_number = StringField('Phone number', validators=[DataRequired(), Length(min=10, max=15)])
    website= TextAreaField('Website (Optional)')
    address= TextAreaField('Club Address')
    submit = SubmitField('Sign Up')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is already in use. Please choose a different one.')

class SiteAdminRegistrationForm(FlaskForm):
    """Form for the first site admin to register with a simple username and password."""
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    submit = SubmitField('Create Admin Account')

    def validate_username(self, username):
        """Check if the username is already taken."""
        admin = SiteAdmin.query.filter_by(username=username.data).first()
        if admin:
            raise ValidationError('That username is already in use.')


class BroadcastNotificationForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=3, max=100)])
    body = TextAreaField('Body', validators=[DataRequired(), Length(min=10, max=250)])
    submit = SubmitField('Send Notification')


class EditLeagueForm(FlaskForm):
    name = StringField('League Name', validators=[DataRequired()])
    entry_fee = IntegerField('Entry Fee (€)', validators=[DataRequired(), NumberRange(min=0)])
    max_entries = IntegerField('Max Entries', validators=[DataRequired(), NumberRange(min=2)])
    prize_pool_percentage = IntegerField('Creator Prize Share (%)', validators=[DataRequired(), NumberRange(min=0, max=50)])

    # --- START: New Tour Field ---
    tour = SelectField('Tour', choices=[
        ('pga', 'PGA Tour'),
        ('euro', 'European Tour'),
    ], validators=[DataRequired()])
    # --- END: New Tour Field ---

    submit = SubmitField('Update League')


class ResendVerificationForm(FlaskForm):
    email = StringField(
        'Email Address',
        validators=[
            DataRequired(message="Email address is required."),
            Email(message="Please enter a valid email address.")
        ],
        render_kw={"placeholder": "Enter your email address", "autocomplete": "email"}
    )
    submit = SubmitField('Send Verification Email')

class BroadcastNotificationForm(FlaskForm):
    title = StringField('Notification Title', validators=[
        DataRequired(message="Title is required"),
        Length(min=1, max=100, message="Title must be between 1 and 100 characters")
    ])

    body = TextAreaField('Message Body', validators=[
        DataRequired(message="Message body is required"),
        Length(min=1, max=500, message="Message must be between 1 and 500 characters")
    ])

    notification_type = SelectField('Notification Type', choices=[
        ('broadcast', 'General Broadcast'),
        ('announcement', 'Important Announcement'),
        ('tournament_update', 'Tournament Update'),
        ('system_notice', 'System Notice'),
        ('marketing', 'Marketing Message')
    ], default='broadcast')

    priority = SelectField('Priority Level', choices=[
        ('normal', 'Normal'),
        ('high', 'High Priority (Requires Interaction)')
    ], default='normal', description='High priority notifications require user interaction and include vibration')

    submit = SubmitField('Send Broadcast Notification')