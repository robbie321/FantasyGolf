# fantasy_league_app/push/services.py
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from flask import current_app
from pywebpush import webpush, WebPushException
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
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

    def _convert_der_private_key(self, base64url_key):
        """Convert base64url VAPID key to bytes - simple conversion"""
        try:
            current_app.logger.info(f"Converting VAPID key, length: {len(base64url_key)}")

            # Add padding if needed
            missing_padding = len(base64url_key) % 4
            if missing_padding:
                base64url_key += '=' * (4 - missing_padding)

            # Convert base64url to standard base64
            standard_b64 = base64url_key.replace('-', '+').replace('_', '/')

            # Decode to bytes
            key_bytes = base64.b64decode(standard_b64)

            # Should be 32 bytes for P-256
            if len(key_bytes) != 32:
                raise ValueError(f"Invalid key length: {len(key_bytes)}, expected 32")

            current_app.logger.info("✅ VAPID key converted successfully")
            return key_bytes

        except Exception as e:
            current_app.logger.error(f"Key conversion failed: {e}")
            return None

    def generate_new_vapid_keys():
        """Generate new VAPID keys in base64url format"""
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.backends import default_backend
            import base64

            # Generate private key
            private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

            # Get raw private key bytes (32 bytes)
            private_numbers = private_key.private_numbers()
            raw_private_bytes = private_numbers.private_value.to_bytes(32, byteorder='big')

            # Get public key
            public_key = private_key.public_key()
            public_numbers = public_key.public_numbers()

            # Convert public key to uncompressed format (65 bytes: 0x04 + 32 bytes X + 32 bytes Y)
            x_bytes = public_numbers.x.to_bytes(32, byteorder='big')
            y_bytes = public_numbers.y.to_bytes(32, byteorder='big')
            raw_public_bytes = b'\x04' + x_bytes + y_bytes

            # Encode as base64url (the modern format)
            private_base64url = base64.urlsafe_b64encode(raw_private_bytes).decode('utf-8').rstrip('=')
            public_base64url = base64.urlsafe_b64encode(raw_public_bytes).decode('utf-8').rstrip('=')

            return private_base64url, public_base64url

        except Exception as e:
            print(f"Error generating VAPID keys: {e}")
            return None, None



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
        """Send push notification synchronously (for immediate sending)"""

        # Get VAPID configuration
        vapid_private_key = current_app.config.get('VAPID_PRIVATE_KEY')  # Keep as string
        vapid_claims_email = current_app.config.get('VAPID_CLAIM_EMAIL')

        if not vapid_private_key or not vapid_claims_email:
            current_app.logger.error("VAPID configuration missing")
            return {"error": "VAPID keys not configured", "success": 0, "failed": 0}

        current_app.logger.info(f"Sending notifications to {len(user_ids)} users")

        # Filter users based on preferences
        filtered_users = self._filter_users_by_preferences(user_ids, notification_type)

        if not filtered_users:
            return {"success": 0, "failed": 0, "message": "No users with matching preferences"}

        # Get active subscriptions for filtered users
        subscriptions = PushSubscription.query.filter(
            PushSubscription.user_id.in_(filtered_users)
        ).all()

        if not subscriptions:
            current_app.logger.warning("No active subscriptions found")
            return {"success": 0, "failed": 0, "message": "No active subscriptions found"}

        current_app.logger.info(f"Found {len(subscriptions)} active subscriptions")

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

        # Send notifications using converted key
        results = self._send_to_subscriptions_with_string_key(
            subscriptions, payload, vapid_private_key, vapid_claims_email
        )

        return results

    def _send_to_subscriptions_with_raw_key(self, subscriptions, payload, vapid_private_key, vapid_claim_email):
        """Send notification to multiple subscriptions using string key"""

        success_count = 0
        failed_count = 0

        for subscription in subscriptions:
            try:
                subscription_data = subscription.to_dict()
                if not subscription_data:
                    failed_count += 1
                    current_app.logger.warning(f"Invalid subscription data for subscription {subscription.id}")
                    continue

                current_app.logger.info(f"Sending push to endpoint: {subscription_data.get('endpoint', 'unknown')[:50]}...")

                # Pass the base64url string directly - pywebpush 2.1.0 handles conversion
                webpush(
                    subscription_info=subscription_data,
                    data=json.dumps(payload),
                    vapid_private_key=vapid_private_key,  # Pass string, not bytes
                    vapid_claims={
                        "sub": vapid_claim_email
                    }
                )

                success_count += 1
                current_app.logger.info(f"✅ Push notification sent successfully to user {subscription.user_id}")

                # Log successful notification
                self._log_notification(
                    subscription.user_id,
                    subscription.id,
                    payload,
                    'sent'
                )

            except WebPushException as e:
                failed_count += 1
                error_msg = f"WebPush error: {str(e)}"

                current_app.logger.error(f"❌ WebPush failed for user {subscription.user_id}: {error_msg}")

                # Handle expired/invalid subscriptions
                if e.response and e.response.status_code in [400, 404, 410]:
                    try:
                        current_app.logger.info(f"Removing invalid subscription {subscription.id}")
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
                error_msg = f"General error: {str(e)}"
                current_app.logger.error(f"❌ Push notification failed for user {subscription.user_id}: {error_msg}")

                self._log_notification(
                    subscription.user_id,
                    subscription.id,
                    payload,
                    'failed',
                    error_msg
                )

        current_app.logger.info(f"Push notification results: {success_count} success, {failed_count} failed")

        return {
            "success": success_count,
            "failed": failed_count,
            "total": len(subscriptions)
        }


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


def convert_der_to_raw_private_key(der_base64_key):
    """Convert DER-encoded private key to raw bytes for pywebpush"""
    try:
        # Decode base64
        der_bytes = base64.b64decode(der_base64_key)

        # Load the DER-encoded private key
        private_key = serialization.load_der_private_key(der_bytes, password=None)

        # Extract raw private key bytes (32 bytes for P-256)
        private_numbers = private_key.private_numbers()
        private_bytes = private_numbers.private_value.to_bytes(32, byteorder='big')

        return private_bytes

    except Exception as e:
        print(f"Error converting private key: {e}")
        return None

def convert_der_to_raw_public_key(der_base64_key):
    """Convert DER-encoded public key to raw bytes"""
    try:
        # Decode base64
        der_bytes = base64.b64decode(der_base64_key)

        # Find the uncompressed point (starts with 0x04)
        point_start = der_bytes.find(b'\x04')
        if point_start == -1:
            raise ValueError("Could not find uncompressed point in DER data")

        # Extract the 65-byte uncompressed point
        public_key_bytes = der_bytes[point_start:point_start + 65]

        if len(public_key_bytes) != 65:
            raise ValueError(f"Invalid public key length: {len(public_key_bytes)}")

        return public_key_bytes

    except Exception as e:
        print(f"Error converting public key: {e}")
        return None

def send_broadcast_notification(self, title, body, notification_type='broadcast', **kwargs):
    """Send notification to all subscribed users"""
    try:
        from fantasy_league_app.models import User

        # Get all active users
        active_users = User.query.filter_by(is_active=True).all()
        user_ids = [user.id for user in active_users]

        if not user_ids:
            return {'success': 0, 'failed': 0, 'total': 0, 'message': 'No active users found'}

        current_app.logger.info(f"Broadcasting notification to {len(user_ids)} users")

        # Send using the existing sync method
        result = self.send_notification_sync(
            user_ids=user_ids,
            notification_type=notification_type,
            title=title,
            body=body,
            **kwargs
        )

        current_app.logger.info(f"Broadcast complete: {result}")
        return result

    except Exception as e:
        current_app.logger.error(f"Broadcast notification error: {e}")
        return {'success': 0, 'failed': 0, 'total': 0, 'error': str(e)}

# Test your current keys
def test_current_vapid_keys():
    """Test and convert your current VAPID keys"""

    # Your current keys from config.py
    current_private = 'MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgJEK++bJ3qsf4NV4jkIHX/RHFlzs0ZlaBe7AK8F865T6hRANCAAQyKR43hjnqpSX00q1vq++d4mz7QELsN8pcmUJAYJjbepEqXm4lLfpzdJYmpVW+/p6j7mu+Cc05vxG/V1Qpx0Rl'
    current_public = 'MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEMikeN4Y56qUl9NKtb6vvneJs+0BC7DfKXJlCQGCY23qRKl5uJS36c3SWJqVVvv6eo+5rvgnNOb8Rv1dUKcdEZQ=='

    print("=== VAPID Key Conversion Test ===")

    # Convert private key
    raw_private = convert_der_to_raw_private_key(current_private)
    if raw_private:
        print(f"✅ Private key converted successfully")
        print(f"   Raw private key length: {len(raw_private)} bytes")
        print(f"   Base64 encoded: {base64.b64encode(raw_private).decode()}")
    else:
        print("❌ Private key conversion failed")

    # Convert public key
    raw_public = convert_der_to_raw_public_key(current_public)
    if raw_public:
        print(f"✅ Public key converted successfully")
        print(f"   Raw public key length: {len(raw_public)} bytes")
        print(f"   Base64 encoded: {base64.b64encode(raw_public).decode()}")
    else:
        print("❌ Public key conversion failed")

    return raw_private, raw_public

if __name__ == "__main__":
    test_current_vapid_keys()