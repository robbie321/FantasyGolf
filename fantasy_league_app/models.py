# --- File: fantasy_league_app/models.py (UPDATED - Add Tie-Breaker Question to League and Answer to LeagueEntry) ---
from datetime import datetime, timedelta
from flask_login import UserMixin
from fantasy_league_app import db
import random

# Association table for Player and PlayerBucket (Many-to-Many)
player_bucket_association = db.Table(
    'player_bucket_association',
    db.Column('player_id', db.Integer, db.ForeignKey('players.id'), primary_key=True),
    db.Column('player_bucket_id', db.Integer, db.ForeignKey('player_buckets.id'), primary_key=True)
)

# used incase a league cannot be settled so many users may receive a split of the prize pool
league_winners_association = db.Table('league_winners',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('league_id', db.Integer, db.ForeignKey('leagues.id'), primary_key=True)
)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_club_admin = db.Column(db.Boolean, default=False)
    is_site_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    password_reset_required = db.Column(db.Boolean, nullable=False, default=False)
    total_winnings = db.Column(db.Float, default=0.0)
    stripe_account_id = db.Column(db.String(255), nullable=True)

    def get_id(self):
        return f"{self.id}-user"

    def __repr__(self):
        return f'<User {self.email}>'

class Club(db.Model, UserMixin):
    __tablename__ = 'clubs'
    id = db.Column(db.Integer, primary_key=True)
    club_name = db.Column(db.String(150), unique=True, nullable=False)
    contact_person = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(20))
    website = db.Column(db.String(200))
    address = db.Column(db.String(250))
    password_hash = db.Column(db.String(255), nullable=False)
    created_leagues = db.relationship('League', backref='club_host', lazy=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    password_reset_required = db.Column(db.Boolean, nullable=False, default=False)
    stripe_account_id = db.Column(db.String(255), nullable=True)

    @property
    def is_club_admin(self):
        return True

    def get_id(self):
        return f"{self.id}-club"

    def __repr__(self):
        return f'<Club {self.club_name}>'

class SiteAdmin(db.Model, UserMixin):
    __tablename__ = 'site_admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def get_id(self):
        return f"{self.id}-site_admin"

    @property
    def is_site_admin(self):
        return True

    @property
    def is_club_admin(self):
        return False

    @property
    def full_name(self):
        return self.username

    def __repr__(self):
        return f'<SiteAdmin {self.username}>'

class PlayerBucket(db.Model):
    __tablename__ = 'player_buckets'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    event_id = db.Column(db.String(50), nullable=True)
    tour = db.Column(db.String(10), nullable=False)
    # Many-to-many relationship with Player
    players = db.relationship('Player', secondary=player_bucket_association, back_populates='player_buckets')
    # Relationship to leagues that use this bucket (one-to-many from League to PlayerBucket)
    leagues = db.relationship('League', backref='player_bucket', lazy=True)

    def get_random_player_for_tie_breaker(self):
        """Selects a random player from the bucket."""
        if self.players:
            return random.choice(self.players)
        return None

    def __repr__(self):
        return f'<PlayerBucket {self.name}>'

class Player(db.Model):
    __tablename__ = 'players'
    id = db.Column(db.Integer, primary_key=True)
    dg_id = db.Column(db.Integer, unique=True, nullable=True) # Nullable for manually added players
    name = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
    odds = db.Column(db.Float, default=0.0)
    current_score = db.Column(db.Integer, default=0)
    tee_time = db.Column(db.String(20), nullable=True) # To store tee times like "13:45"
    # NEW: Many-to-many relationship with PlayerBucket
    player_buckets = db.relationship('PlayerBucket', secondary=player_bucket_association, back_populates='players')

    def __repr__(self):
        return f'<Player {self.name} {self.surname} ({self.odds:.2f})>'

    def full_name(self):
        return f'{self.name} {self.surname}'


# --- Model to store historical player scores for finalized leagues ---
class PlayerScore(db.Model):
    __tablename__ = 'player_scores'
    id = db.Column(db.Integer, primary_key=True)
    score = db.Column(db.Integer, nullable=False)

    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    league_id = db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=False)

    player = db.relationship('Player')
    league = db.relationship('League')

    def __repr__(self):
        return f'<PlayerScore {self.player.full_name()} in {self.league.name}: {self.score}>'

class League(db.Model):
    __tablename__ = 'leagues'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    league_code = db.Column(db.String(10), unique=True, nullable=False)
    entry_fee = db.Column(db.Float, default=0.0)
    prize_amount = db.Column(db.Integer, nullable=False, default=10)
    prize_details = db.Column(db.Text)
    rules = db.Column(db.Text)
    tie_breaker_question = db.Column(db.String(255), nullable=False, default="Enter a question")
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)

    is_finalized = db.Column(db.Boolean, default=False, nullable=False)
    tie_breaker_actual_answer = db.Column(db.Integer, nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    is_public = db.Column(db.Boolean, default=False, nullable=False)
    # Make the existing user_id nullable
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Add a new nullable site_admin_id foreign key
    site_admin_id = db.Column(db.Integer, db.ForeignKey('site_admins.id'), nullable=True)
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=True) # Now nullable
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # New column for user-created leagues
    player_bucket_id = db.Column(db.Integer, db.ForeignKey('player_buckets.id'), nullable=True)
    entries = db.relationship('LeagueEntry', backref='league', lazy=True)

    tour = db.Column(db.String(10), nullable=False, default='pga')

    tie_breaker_player_id = db.Column(db.Integer, nullable=True)

    #Track email reminder 24h before start of league
    reminder_sent = db.Column(db.Boolean, default=False, nullable=False)

    payout_status = db.Column(db.String(20), default='pending', nullable=True) # Values: 'pending', 'paid'

    # custom rules
    max_entries = db.Column(db.Integer, nullable=True)  # Max number of users, nullable for unlimited
    odds_limit = db.Column(db.Integer, nullable=True)   # Max combined odds, nullable for no limit
    no_favorites_rule = db.Column(db.Boolean, default=False, nullable=False) # Number of top players to exclude (0 = no rule)

    #reltionships
    winner = db.relationship('User', foreign_keys=[winner_id])
    creator = db.relationship('User', foreign_keys=[user_id])
    winners = db.relationship('User', secondary=league_winners_association, backref='won_leagues')

    @property
    def creator_name(self):
        """Returns the name of the league creator."""
        if self.club_host:
            return self.club_host.club_name
        elif self.creator:
            return self.creator.full_name
        else:
            return "Site Admin" #public league

    # deadline logic
    @property
    def entry_deadline(self):
        """Calculates the deadline for entries (12 hours before start_date)."""
        return self.start_date - timedelta(hours=12)

    @property
    def has_entry_deadline_passed(self):
        """Checks if the current time is past the entry deadline."""
        return datetime.utcnow() >= self.entry_deadline

    # --- NEW PROPERTY TO ADD ---
    @property
    def has_ended(self):
        """Checks if the current time is past the league's end_date."""
        return datetime.utcnow() >= self.end_date

    def __repr__(self):
        return f'<League {self.name}>'



class LeagueEntry(db.Model):
    __tablename__ = 'league_entries'
    id = db.Column(db.Integer, primary_key=True)

    entry_name = db.Column(db.String(150), nullable=False)

    total_odds = db.Column(db.Float, default=0.0)
    # NEW: Tie-breaker answer for the entry
    tie_breaker_answer = db.Column(db.Integer, nullable=True) # Changed to Integer for numerical answers
    created_at = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)
    league_id = db.Column(db.Integer, db.ForeignKey('leagues.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    player1_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    player3_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)

    # current_rank = db.Column(db.Integer, nullable=True)

    player1 = db.relationship('Player', foreign_keys=[player1_id], backref='entries_as_player1', lazy=True)
    player2 = db.relationship('Player', foreign_keys=[player2_id], backref='entries_as_player2', lazy=True)
    player3 = db.relationship('Player', foreign_keys=[player3_id], backref='entries_as_player3', lazy=True)

    user = db.relationship('User', backref='league_entries_user', lazy=True)

    @property
    def display_entry_name(self):
        """Dynamically generates the entry name based on the associated user/club."""
        from fantasy_league_app.models import Club # Import here to avoid circular dependency
        if self.user:
            # Check if the user is associated with a club (as a club admin)
            # This logic might need refinement if a regular user can also be part of a club
            # For now, assuming if user_id matches a club_id, it's a club admin.
            # This is a simplification and might need a more robust way to link users to clubs.
            potential_club = Club.query.get(self.user_id) # This is incorrect, user_id is for User, not Club.
                                                        # A LeagueEntry is made by a User, not a Club.
                                                        # The display_entry_name should just be the user's full name.
            # Corrected logic: display user's full name. If a club admin creates an entry, it's still linked to a User record.
            return self.user.full_name
        return "Unknown Participant"

    def __repr__(self):
        return f'<LeagueEntry {self.display_entry_name} in {self.league.name}>'



class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subscription_json = db.Column(db.Text, nullable=False)

    @property
    def endpoint(self):
        import json
        return json.loads(self.subscription_json).get('endpoint')


