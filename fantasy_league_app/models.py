# --- File: fantasy_league_app/models.py (UPDATED - Add Tie-Breaker Question to League and Answer to LeagueEntry) ---
from datetime import datetime, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
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
    __table_args__ = (
        db.Index('idx_user_email', 'email'),  # For login queries
        db.Index('idx_user_active', 'is_active'),  # For filtering active users
        db.Index('idx_user_admin_flags', 'is_club_admin', 'is_site_admin'),  # For admin checks
    )
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

    created_leagues = db.relationship('League', back_populates='creator', foreign_keys='League.creator_id')
    # created_public_leagues = db.relationship('League', back_populates='site_admin', foreign_keys='League.site_admin_id')

    def get_id(self):
        return f"user-{self.id}"


    def set_password(self, password):
        """Creates a hashed password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Checks if the provided password matches the hash."""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'

    @cache_result('user_data', lambda self: CacheManager.cache_key_for_user_leagues(self.id))
    def get_active_leagues(self):
        """Cached list of user's active leagues"""
        return League.query.join(LeagueEntry).filter(
            LeagueEntry.user_id == self.id,
            League.is_finalized == False
        ).all()

    @cache_result('user_data')
    def get_league_stats(self):
        """Cached user statistics"""
        total_entries = LeagueEntry.query.filter_by(user_id=self.id).count()
        active_entries = LeagueEntry.query.join(League).filter(
            LeagueEntry.user_id == self.id,
            League.is_finalized == False
        ).count()

        return {
            'total_entries': total_entries,
            'active_entries': active_entries,
            'total_winnings': self.total_winnings
        }

    def invalidate_cache(self):
        """Invalidate all cached data for this user"""
        cache.delete(CacheManager.cache_key_for_user_leagues(self.id))

class Club(db.Model, UserMixin):
    __tablename__ = 'clubs'
    __table_args__ = (
        db.Index('idx_club_email', 'email'),  # For login queries
        db.Index('idx_club_active', 'is_active'),  # For filtering active clubs
        db.Index('idx_club_name', 'club_name'),  # For club name searches
    )
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

    def set_password(self, password):
        """Creates a hashed password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Checks if the provided password matches the hash."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_club_admin(self):
        return True

    def get_id(self):
        return f"club-{self.id}"


    def to_dict(self):
        return {
            'id': self.id,
            'club_name': self.club_name,
            'email': self.email
        }

    def __repr__(self):
        return f'<Club {self.club_name}>'

class SiteAdmin(db.Model, UserMixin):
    __tablename__ = 'site_admins'
    __table_args__ = (
        db.Index('idx_admin_username', 'username'),
    )
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def get_id(self):
        return f"admin-{self.id}"

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
    __table_args__ = (
        db.Index('idx_bucket_tour', 'tour'),  # For filtering by tour
        db.Index('idx_bucket_created', 'created_at'),  # For date-based queries
        db.Index('idx_bucket_event', 'event_id'),  # For event-specific lookups
    )
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
    __table_args__ = (
        db.Index('idx_player_dg_id', 'dg_id'),  # For API data updates
        db.Index('idx_player_name_search', 'name', 'surname'),  # For player searches
        db.Index('idx_player_odds', 'odds'),  # For odds-based filtering
        db.Index('idx_player_score', 'current_score'),  # For leaderboard queries
    )
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

    @staticmethod
    @cache_result('player_scores', lambda tour: CacheManager.cache_key_for_player_scores(tour))
    def get_players_by_tour_cached(tour):
        """Cached player list for a specific tour"""
        return Player.query.join(player_bucket_association).join(PlayerBucket).filter(
            PlayerBucket.tour == tour
        ).all()

# --- Model to store historical player scores for finalized leagues ---
class PlayerScore(db.Model):
    __tablename__ = 'player_scores'
    __table_args__ = (
        db.Index('idx_score_league_player', 'league_id', 'player_id'),  # For score lookups
        db.Index('idx_score_league', 'league_id'),  # For league-specific queries
    )
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
    __table_args__ = (
        db.Index('idx_league_dates', 'start_date', 'end_date'),  # For date-based filtering
        db.Index('idx_league_status', 'is_finalized'),  # For status filtering
        db.Index('idx_league_public', 'is_public'),  # For public/private filtering
        db.Index('idx_league_creator', 'creator_id'),  # For creator queries
        db.Index('idx_league_club', 'club_id'),  # For club queries
        db.Index('idx_league_tour', 'tour'),  # For tour-based filtering
        db.Index('idx_league_code', 'league_code'),  # For league code lookups
        db.Index('idx_league_fees', 'fees_processed'),  # For fee processing queries
        db.Index('idx_league_payout', 'payout_status'),  # For payout tracking
        db.Index('idx_league_active', 'start_date', 'end_date', 'is_finalized'),  # Composite for active leagues
    )
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
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    is_finalized = db.Column(db.Boolean, default=False, nullable=False)
    tie_breaker_actual_answer = db.Column(db.Integer, nullable=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    is_public = db.Column(db.Boolean, default=False, nullable=False)
    # Make the existing user_id nullable
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


    # Add a new nullable site_admin_id foreign key
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

    fees_processed = db.Column(db.Boolean, default=False, nullable=False)

    #reltionships
    winner = db.relationship('User', foreign_keys=[winner_id])
    winners = db.relationship('User', secondary=league_winners_association, backref='won_leagues')
    creator = db.relationship('User', back_populates='created_leagues', foreign_keys=[creator_id])

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

    def to_dict(self):
        # Determine the league's current status
        now = datetime.utcnow()
        status = "Upcoming"
        if self.is_finalized:
            status = "Past"
        elif self.start_date and now > self.start_date:
            status = "Live"

        return {
            'id': self.id,
            'name': self.name,
            'league_code': self.league_code,
            'entries': len(self.entries),
            'status': status,
            'tour' : self.tour,
            # 'ends' : self.end_date,
            'prizePool' : self.prize_amount,
            'entryFee' : self.entry_fee
            # This is a cleaner set of data for the club dashboard's JS
        }


    def __repr__(self):
        return f'<League {self.name}>'

    @property
    @cache_result('league_data', lambda self: CacheManager.cache_key_for_league_entries(self.id))
    def entry_count(self):
        """Cached entry count to avoid repeated queries"""
        return LeagueEntry.query.filter_by(league_id=self.id).count()

    @property
    @cache_result('league_data')
    def total_prize_pool(self):
        """Cached prize pool calculation"""
        return self.entry_fee * self.entry_count

    @cache_result('leaderboards', lambda self: CacheManager.cache_key_for_leaderboard(self.id))
    def get_leaderboard(self):
        """Cached leaderboard calculation"""
        entries = self.entries
        leaderboard_data = []

        for entry in entries:
            total_score = 0
            if entry.player1 and entry.player1.current_score is not None:
                total_score += entry.player1.current_score
            if entry.player2 and entry.player2.current_score is not None:
                total_score += entry.player2.current_score
            if entry.player3 and entry.player3.current_score is not None:
                total_score += entry.player3.current_score

            leaderboard_data.append({
                'entry_id': entry.id,
                'user_name': entry.user.full_name,
                'total_score': total_score,
                'players': [
                    {'name': entry.player1.full_name(), 'score': entry.player1.current_score},
                    {'name': entry.player2.full_name(), 'score': entry.player2.current_score},
                    {'name': entry.player3.full_name(), 'score': entry.player3.current_score}
                ]
            })

        # Sort by total score (lowest first in golf)
        leaderboard_data.sort(key=lambda x: x['total_score'])

        # Add positions
        for i, entry in enumerate(leaderboard_data):
            entry['position'] = i + 1

        return leaderboard_data

    def invalidate_cache(self):
        """Invalidate all cached data for this league"""
        cache.delete(CacheManager.cache_key_for_league_entries(self.id))
        cache.delete(CacheManager.cache_key_for_leaderboard(self.id))

class LeagueEntry(db.Model):
    __tablename__ = 'league_entries'

    __table_args__ = (
        db.Index('idx_entry_league_user', 'league_id', 'user_id'),  # For user entries in league
        db.Index('idx_entry_league', 'league_id'),  # For league-specific queries
        db.Index('idx_entry_user', 'user_id'),  # For user-specific queries
        db.Index('idx_entry_fee_status', 'fee_collected'),  # For fee processing
        db.Index('idx_entry_created', 'created_at'),  # For time-based queries
        db.Index('idx_entry_players', 'player1_id', 'player2_id', 'player3_id'),  # For player queries
    )

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

    fee_collected = db.Column(db.Boolean, default=False, nullable=False)

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
    __tablename__ = 'push_subscriptions'

    # Index for user lookups
    __table_args__ = (
        db.Index('idx_push_user', 'user_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subscription_json = db.Column(db.Text, nullable=False)

    @property
    def endpoint(self):
        import json
        return json.loads(self.subscription_json).get('endpoint')


class DailyTaskTracker(db.Model):
    """Tracks whether a daily scheduled task has been successfully run."""

    __table_args__ = (
        db.Index('idx_task_date', 'task_name', 'run_date'),  # For daily task checks
        db.Index('idx_task_created', 'created_at'),  # For cleanup queries
    )

    id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(100), nullable=False)
    run_date = db.Column(db.Date, nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DailyTaskTracker {self.task_name} on {self.run_date}>'
