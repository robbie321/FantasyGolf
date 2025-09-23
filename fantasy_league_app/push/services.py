# fantasy_league_app/push/services.py
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from flask import current_app
from pywebpush import webpush, WebPushException

from fantasy_league_app.extensions import db
from fantasy_league_app.models import PushSubscription
from .models import NotificationLog, NotificationTemplate, NotificationPreference


class PushNotificationService:
    """Enhanced push notification service for Fantasy Golf"""

    def __init__(self):
        self.app = None

    def init_app(self, app):
        """Initialize service with Flask app"""
        self.app = app

        # Validate configuration
        if not self._validate_config(app):
            current_app.logger.error("Push notification configuration invalid")

    def _validate_config(self, app):
        """Validate VAPID configuration"""
        required_keys = ['VAPID_PRIVATE_KEY', 'VAPID_PUBLIC_KEY', 'VAPID_CLAIM_EMAIL']

        for key in required_keys:
            if not app.config.get(key):
                app.logger.error(f"Missing push notification config: {key}")
                return False

        return True

    def send_notification(
        self,
        user_ids: List[int],
        notification_type: str,
        title: str,
        body: str,
        data: Optional[Dict] = None,
        url: Optional[str] = None,
        icon: Optional[str] = None,
        badge: Optional[str] = None,
        actions: Optional[List[Dict]] = None,
        require_interaction: bool = False,
        tag: Optional[str] = None,
        vibrate: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Send push notification to multiple users
        Integrates with your existing Celery setup for background processing
        """

        # Use Celery for background processing
        from fantasy_league_app.tasks import send_push_notification_task

        # Queue the notification sending as a background task
        task = send_push_notification_task.delay(
            user_ids=user_ids,
            notification_type=notification_type,
            title=title,
            body=body,
            data=data,
            url=url,
            icon=icon,
            badge=badge,
            actions=actions,
            require_interaction=require_interaction,
            tag=tag,
            vibrate=vibrate
        )

        return {
            'task_id': task.id,
            'status': 'queued',
            'user_count': len(user_ids)
        }

    def send_notification_sync(
        self,
        user_ids: List[int],
        notification_type: str,
        title: str,
        body: str,
        data: Optional[Dict] = None,
        url: Optional[str] = None,
        icon: Optional[str] = None,
        badge: Optional[str] = None,
        actions: Optional[List[Dict]] = None,
        require_interaction: bool = False,
        tag: Optional[str] = None,
        vibrate: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Send push notification synchronously (for immediate sending)
        """

        if not current_app.config.get('VAPID_PRIVATE_KEY'):
            return {"error": "VAPID keys not configured", "success": 0, "failed": 0}

        # Filter users based on preferences
        filtered_users = self._filter_users_by_preferences(user_ids, notification_type)

        if not filtered_users:
            return {"success": 0, "failed": 0, "message": "No users with matching preferences"}

        # Get active subscriptions for filtered users
        subscriptions = PushSubscription.query.filter(
            PushSubscription.user_id.in_(filtered_users)
        ).all()

        if not subscriptions:
            return {"success": 0, "failed": 0, "message": "No active subscriptions found"}

        # Prepare notification payload
        payload = {
            "title": title,
            "body": body,
            "type": notification_type,
            "icon": icon or "/static/images/icon-192x192.png",
            "badge": badge or "/static/images/badge-72x72.png",
            "tag": tag or notification_type,
            "requireInteraction": require_interaction,
            "data": {
                **(data or {}),
                "url": url,
                "timestamp": datetime.utcnow().isoformat(),
                "type": notification_type
            }
        }

        if actions:
            payload["actions"] = actions
        if vibrate:
            payload["vibrate"] = vibrate

        # Send notifications
        results = self._send_to_subscriptions(subscriptions, payload)

        return results

    def _filter_users_by_preferences(self, user_ids: List[int], notification_type: str) -> List[int]:
        """Filter users based on their notification preferences"""

        # Map notification types to preference fields
        type_mapping = {
            'league_update': 'league_updates',
            'score_update': 'score_updates',
            'tournament_start': 'tournament_start',
            'tournament_end': 'tournament_end',
            'prize_won': 'prize_notifications',
            'rank_change': 'score_updates',  # Rank changes are score-related
            'marketing': 'marketing'
        }

        pref_field = type_mapping.get(notification_type)
        if not pref_field:
            # If no mapping, allow all users
            return user_ids

        # Get users who have this preference enabled (or no preference set = default enabled)
        enabled_users = db.session.query(NotificationPreference.user_id).filter(
            NotificationPreference.user_id.in_(user_ids),
            getattr(NotificationPreference, pref_field) == True
        ).all()

        enabled_user_ids = [u[0] for u in enabled_users]

        # Also include users who don't have preferences set (defaults to enabled)
        users_without_prefs = [
            uid for uid in user_ids
            if uid not in [p.user_id for p in NotificationPreference.query.filter(
                NotificationPreference.user_id.in_(user_ids)
            ).all()]
        ]

        return list(set(enabled_user_ids + users_without_prefs))

    def _send_to_subscriptions(
        self,
        subscriptions: List[PushSubscription],
        payload: Dict
    ) -> Dict[str, Any]:
        """Send notification to multiple subscriptions"""

        success_count = 0
        failed_count = 0
        results = []

        for subscription in subscriptions:
            try:
                subscription_data = subscription.to_dict()
                if not subscription_data:
                    failed_count += 1
                    continue

                webpush(
                    subscription_info=subscription_data,
                    data=json.dumps(payload),
                    vapid_private_key=current_app.config['VAPID_PRIVATE_KEY'],
                    vapid_claims={
                        "sub": current_app.config['VAPID_CLAIM_EMAIL']
                    }
                )

                success_count += 1

                # Log successful notification
                self._log_notification(
                    subscription.user_id,
                    subscription.id,
                    payload,
                    'sent'
                )

            except WebPushException as e:
                failed_count += 1
                error_msg = str(e)

                # Handle expired/invalid subscriptions
                if e.response and e.response.status_code in [400, 404, 410]:
                    # Remove invalid subscription
                    try:
                        db.session.delete(subscription)
                        db.session.commit()
                        error_msg = "Subscription expired/invalid - removed"
                    except Exception:
                        db.session.rollback()

                # Log failed notification
                self._log_notification(
                    subscription.user_id,
                    subscription.id,
                    payload,
                    'failed',
                    error_msg
                )

            except Exception as e:
                failed_count += 1
                self._log_notification(
                    subscription.user_id,
                    subscription.id,
                    payload,
                    'failed',
                    str(e)
                )

        return {
            "success": success_count,
            "failed": failed_count,
            "total": len(subscriptions)
        }

    def _log_notification(
        self,
        user_id: int,
        subscription_id: int,
        payload: Dict,
        status: str,
        error_message: str = None
    ):
        """Log notification attempt"""

        try:
            log_entry = NotificationLog(
                user_id=user_id,
                subscription_id=subscription_id,
                notification_type=payload.get("type", "unknown"),
                title=payload["title"],
                body=payload["body"],
                data=json.dumps(payload.get("data", {})),
                status=status,
                error_message=error_message,
                sent_at=datetime.utcnow()
            )

            db.session.add(log_entry)
            db.session.commit()

        except Exception as e:
            current_app.logger.error(f"Failed to log notification: {e}")
            db.session.rollback()

    def send_from_template(
        self,
        user_ids: List[int],
        template_name: str,
        template_data: Dict[str, Any],
        **kwargs
    ):
        """Send notification using a predefined template"""

        template = NotificationTemplate.query.filter_by(
            name=template_name,
            is_active=True
        ).first()

        if not template:
            current_app.logger.error(f"Template '{template_name}' not found")
            return {"error": f"Template '{template_name}' not found", "success": 0, "failed": 0}

        # Render template with data
        try:
            title = template.title_template.format(**template_data)
            body = template.body_template.format(**template_data)
        except KeyError as e:
            current_app.logger.error(f"Missing template data: {e}")
            return {"error": f"Missing template data: {e}", "success": 0, "failed": 0}

        # Parse template settings
        actions = json.loads(template.actions) if template.actions else None
        vibrate = json.loads(template.vibrate_pattern) if template.vibrate_pattern else None

        return self.send_notification_sync(
            user_ids=user_ids,
            notification_type=template.notification_type,
            title=title,
            body=body,
            icon=template.icon,
            badge=template.badge,
            actions=actions,
            require_interaction=template.require_interaction,
            vibrate=vibrate,
            **kwargs
        )


# Initialize service
push_service = PushNotificationService()


# Integration functions for your existing codebase
def send_league_update_notification(league_id: int, message: str):
    """Send notification to all users in a league about an update"""
    try:
        from fantasy_league_app.models import League, LeagueEntry

        # Get all users in the league
        league_users = db.session.query(LeagueEntry.user_id).filter(
            LeagueEntry.league_id == league_id
        ).all()
        user_ids = [user[0] for user in league_users]

        if user_ids:
            league = League.query.get(league_id)
            if league:
                push_service.send_from_template(
                    user_ids=user_ids,
                    template_name='league_update',
                    template_data={
                        'message': message,
                        'league_id': league_id,
                        'league_name': league.name
                    },
                    url=f'/league/{league_id}'
                )
    except Exception as e:
        current_app.logger.error(f"Failed to send league update notification: {e}")


def send_score_update_notification(user_ids: List[int], player_name: str, score_change: int):
    """Send score update notification"""
    try:
        score_text = f"{score_change:+d}" if score_change != 0 else "E"

        push_service.send_from_template(
            user_ids=user_ids,
            template_name='score_update',
            template_data={
                'player_name': player_name,
                'score_change': score_text
            },
            url='/dashboard#leaderboards'
        )
    except Exception as e:
        current_app.logger.error(f"Failed to send score update notification: {e}")


def send_tournament_start_notification(tournament_name: str = None):
    """Send notification when tournament starts"""
    try:
        from fantasy_league_app.models import User

        # Get all active users (or users with active leagues)
        active_users = User.query.filter_by(is_active=True).all()
        user_ids = [user.id for user in active_users]

        if user_ids:
            push_service.send_from_template(
                user_ids=user_ids,
                template_name='tournament_start',
                template_data={
                    'tournament_name': tournament_name or 'This Week\'s Tournament'
                },
                url='/dashboard#leaderboards'
            )
    except Exception as e:
        current_app.logger.error(f"Failed to send tournament start notification: {e}")


def send_rank_change_notification(user_id: int, league_name: str, new_rank: int, old_rank: int = None):
    """Send notification for significant rank changes"""
    try:
        # Determine notification type based on rank change
        if new_rank == 1:
            template_name = 'rank_change_leader'
            template_data = {'league_name': league_name}
        elif old_rank and old_rank - new_rank >= 5:  # Moved up 5+ positions
            template_name = 'rank_change_up'
            template_data = {'new_rank': new_rank, 'league_name': league_name}
        else:
            # Don't send notification for minor changes
            return

        push_service.send_from_template(
            user_ids=[user_id],
            template_name=template_name,
            template_data=template_data,
            url='/dashboard'
        )
    except Exception as e:
        current_app.logger.error(f"Failed to send rank change notification: {e}")


def send_prize_won_notification(user_id: int, prize_amount: float, league_name: str):
    """Send notification when user wins a prize"""
    try:
        push_service.send_from_template(
            user_ids=[user_id],
            template_name='prize_won',
            template_data={
                'prize_amount': f"{prize_amount:.2f}",
                'league_name': league_name
            },
            url='/dashboard'
        )
    except Exception as e:
        current_app.logger.error(f"Failed to send prize won notification: {e}")