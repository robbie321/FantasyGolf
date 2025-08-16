from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField, TextAreaField, IntegerField, HiddenField, DateField, DecimalField
from wtforms.validators import DataRequired, NumberRange, Email, EqualTo, ValidationError, Length

class LeagueForm(FlaskForm):
    """
    A unified form for creating and editing leagues for both
    club and site admins.
    """
    name = StringField('League Name', validators=[DataRequired()])
    tour = SelectField('Select Tour', choices=[
        ('pga', 'PGA Tour'),
        ('euro', 'DP World Tour'),
        ('liv', 'LIV Golf')
    ], validators=[DataRequired()])
    start_date = DateField('Tournament Start Date', format='%Y-%m-%d', validators=[DataRequired()])
    player_bucket_id = SelectField('Player Pool', coerce=int, validators=[DataRequired()])
    entry_fee = DecimalField('Entry Fee (€)', places=2, validators=[DataRequired(), NumberRange(min=0)])
    prize_amount = IntegerField(
        'Prize Payout (%)',
        validators=[DataRequired(), NumberRange(min=10, max=100)],
        description="Percentage of the creator's 70% revenue share to be paid out."
    )
    max_entries = IntegerField('Max Entries', validators=[DataRequired(), NumberRange(min=1)])
    odds_limit = IntegerField('Combined Odds Limit', validators=[DataRequired(), NumberRange(min=0)])
    prize_details = TextAreaField('Prize Details')
    rules = TextAreaField('Rules')
    # tie_breaker_question = StringField('Tie-Breaker Question', validators=[DataRequired()])
    no_favorites_rule = BooleanField("Enforce 'No Favorites' Rule")
    submit = SubmitField('Create League')


class SiteAdminRegistrationForm(FlaskForm):
    """Form for the first site admin to register."""
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match.')]
    )
    submit = SubmitField('Create Admin Account')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is already in use. Please choose a different one.')