# fantasy_league_app/push/models.py
import json
from datetime import datetime
from fantasy_league_app.extensions import db


# Enhance your existing PushSubscription model
class PushSubscriptionEnhanced:
    """
    Methods to enhance your existing PushSubscription model
    Add these to your existing PushSubscription class in models.py
    """

    @property
    def endpoint(self):
        """Extract endpoint from stored JSON"""
        try:
            data = json.loads(self.subscription_json)
            return data.get('endpoint', '')
        except (json.JSONDecodeError, TypeError):
            return ''

    @property
    def p256dh_key(self):
        """Extract p256dh key from stored JSON"""
        try:
            data = json.loads(self.subscription_json)
            return data.get('keys', {}).get('p256dh', '')
        except (json.JSONDecodeError, TypeError):
            return ''

    @property
    def auth_key(self):
        """Extract auth key from stored JSON"""
        try:
            data = json.loads(self.subscription_json)
            return data.get('keys', {}).get('auth', '')
        except (json.JSONDecodeError, TypeError):
            return ''

    def to_dict(self):
        """Convert to format expected by pywebpush"""
        try:
            return json.loads(self.subscription_json)
        except (json.JSONDecodeError, TypeError):
            return None


# New models to add to your database
class NotificationLog(db.Model):
    """Track all sent notifications for analytics"""
    __tablename__ = 'notification_logs'

    __table_args__ = (
        db.Index('idx_notification_user', 'user_id'),
        db.Index('idx_notification_type', 'notification_type'),
        db.Index('idx_notification_status', 'status'),
        db.Index('idx_notification_sent', 'sent_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('push_subscriptions.id'), nullable=True)
    notification_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text)
    data = db.Column(db.Text)  # JSON data
    status = db.Column(db.String(20), default='pending')  # pending, sent, failed, clicked, dismissed
    error_message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    clicked_at = db.Column(db.DateTime)
    dismissed_at = db.Column(db.DateTime)

    # Relationships
    user = db.relationship('User', backref='notification_logs')
    subscription = db.relationship('PushSubscription', backref='notification_logs')

    def __repr__(self):
        return f'<NotificationLog {self.id}: {self.notification_type}>'


class NotificationTemplate(db.Model):
    """Predefined notification templates"""
    __tablename__ = 'notification_templates'

    __table_args__ = (
        db.Index('idx_template_name', 'name'),
        db.Index('idx_template_type', 'notification_type'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    title_template = db.Column(db.String(255), nullable=False)
    body_template = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)
    icon = db.Column(db.String(255))
    badge = db.Column(db.String(255))
    actions = db.Column(db.Text)  # JSON array of actions
    require_interaction = db.Column(db.Boolean, default=False)
    vibrate_pattern = db.Column(db.String(100))  # JSON array
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<NotificationTemplate {self.name}>'


class NotificationPreference(db.Model):
    """User notification preferences"""
    __tablename__ = 'notification_preferences'

    __table_args__ = (
        db.Index('idx_pref_user', 'user_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)

    # Preference flags
    league_updates = db.Column(db.Boolean, default=True)
    score_updates = db.Column(db.Boolean, default=True)
    tournament_start = db.Column(db.Boolean, default=True)
    tournament_end = db.Column(db.Boolean, default=True)
    prize_notifications = db.Column(db.Boolean, default=True)
    marketing = db.Column(db.Boolean, default=False)
    tee_time_alerts = db.Column(db.Boolean, default=True)
    deadline_alerts = db.Column(db.Boolean, default=True)
    friend_activity = db.Column(db.Boolean, default=True)

    # Relationship
    user = db.relationship('User', backref='notification_preference', uselist=False)

    def __repr__(self):
        return f'<NotificationPreference {self.user_id}>'

    def to_dict(self):
        return {
            'league_updates': self.league_updates,
            'score_updates': self.score_updates,
            'tournament_start': self.tournament_start,
            'tournament_end': self.tournament_end,
            'prize_notifications': self.prize_notifications,
            'marketing': self.marketing,
            'tee_time_alerts': self.tee_time_alerts,
            'deadline_alerts': self.deadline_alerts,
            'friend_activity': self.friend_activity
        }


def create_notification_templates():
    """Create default notification templates"""
    templates = [
        {
            'name': 'league_update',
            'title_template': '🏆 League Update',
            'body_template': '{message}',
            'notification_type': 'league_update',
            'icon': '/static/images/icon-192x192.png',
            'require_interaction': True,
            'actions': json.dumps([
                {'action': 'view-league', 'title': 'View League'},
                {'action': 'dismiss', 'title': 'Dismiss'}
            ])
        },
        {
            'name': 'score_update',
            'title_template': '⛳ Score Update',
            'body_template': '{player_name} shot {score_change} in the latest round',
            'notification_type': 'score_update',
            'icon': '/static/images/icon-192x192.png',
            'vibrate_pattern': json.dumps([100, 50, 100]),
            'actions': json.dumps([
                {'action': 'view-leaderboard', 'title': 'View Leaderboard'}
            ])
        },
        {
            'name': 'tournament_start',
            'title_template': '🚀 Tournament Started!',
            'body_template': '{tournament_name} has begun. Good luck!',
            'notification_type': 'tournament_start',
            'require_interaction': True,
            'vibrate_pattern': json.dumps([200, 100, 200, 100, 200]),
            'actions': json.dumps([
                {'action': 'view-live', 'title': 'Watch Live'},
                {'action': 'view-team', 'title': 'My Team'}
            ])
        },
        {
            'name': 'prize_won',
            'title_template': '🎉 Congratulations!',
            'body_template': 'You won €{prize_amount} in {league_name}!',
            'notification_type': 'prize_won',
            'require_interaction': True,
            'vibrate_pattern': json.dumps([300, 100, 300, 100, 300]),
            'actions': json.dumps([
                {'action': 'view-winnings', 'title': 'View Winnings'}
            ])
        },
        {
            'name': 'rank_change_up',
            'title_template': '📈 You\'re Moving Up!',
            'body_template': 'You jumped to P{new_rank} in {league_name}!',
            'notification_type': 'rank_change',
            'vibrate_pattern': json.dumps([100, 100, 100])
        },
        {
            'name': 'rank_change_leader',
            'title_template': '👑 You\'re Leading!',
            'body_template': 'You moved into 1st place in {league_name}!',
            'notification_type': 'rank_change',
            'require_interaction': True,
            'vibrate_pattern': json.dumps([200, 100, 200])
        },
        {
            'name': 'player_teeing_off',
            'title_template': '⛳ {player_name} is Teeing Off!',
            'body_template': 'Your player {player_name} starts their round in {minutes} minutes',
            'notification_type': 'player_alert',
            'icon': '/static/images/icon-192x192.png',
            'vibrate_pattern': json.dumps([100, 50, 100]),
            'actions': json.dumps([
                {'action': 'view-player', 'title': 'View Stats'},
                {'action': 'view-league', 'title': 'My Leagues'}
            ])
        },
        {
            'name': 'deadline_urgent',
            'title_template': '⏰ Deadline Alert!',
            'body_template': '{league_name} deadline in {hours} hours - {spots_left} spots left!',
            'notification_type': 'deadline_alert',
            'require_interaction': True,
            'icon': '/static/images/icon-192x192.png',
            'vibrate_pattern': json.dumps([200, 100, 200]),
            'actions': json.dumps([
                {'action': 'join-league', 'title': 'Join Now'},
                {'action': 'view-league', 'title': 'View Details'}
            ])
        },
        {
            'name': 'friend_joined',
            'title_template': '👋 {friend_name} Joined a League',
            'body_template': 'Your friend just joined {league_name}. Join them?',
            'notification_type': 'social',
            'icon': '/static/images/icon-192x192.png',
            'actions': json.dumps([
                {'action': 'view-league', 'title': 'View League'},
                {'action': 'dismiss', 'title': 'Maybe Later'}
            ])
        }
    ]

    for template_data in templates:
        existing = NotificationTemplate.query.filter_by(name=template_data['name']).first()
        if not existing:
            template = NotificationTemplate(**template_data)
            db.session.add(template)

    try:
        db.session.commit()
        print("Notification templates created successfully")
    except Exception as e:
        db.session.rollback()
        print(f"Error creating notification templates: {e}")


# Migration commands to add to your existing models.py
def add_push_notification_fields_to_existing_models():
    """
    Add these fields to your existing PushSubscription model in models.py:

    # Add to existing PushSubscription class:
    user_agent = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime, default=datetime.utcnow)

    # Add these methods to existing PushSubscription:
    def to_dict(self):
        try:
            data = json.loads(self.subscription_json)
            return data
        except (json.JSONDecodeError, TypeError):
            return None

    def get_endpoint(self):
        try:
            data = json.loads(self.subscription_json)
            return data.get('endpoint', '')
        except (json.JSONDecodeError, TypeError):
            return ''
    """
    pass