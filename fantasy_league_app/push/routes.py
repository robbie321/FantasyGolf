# fantasy_league_app/push/routes.py
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from fantasy_league_app.extensions import db, limiter
from fantasy_league_app.models import PushSubscription
from .models import NotificationLog, NotificationPreference
from .services import push_service

# Create blueprint
push_bp = Blueprint('push', __name__, url_prefix='/api/push')


@push_bp.route('/subscribe', methods=['POST'])
@login_required
@limiter.limit("10 per minute")  # Using your existing rate limiter
def subscribe():
    """Subscribe user to push notifications"""
    try:
        data = request.get_json()

        if not data or 'subscription' not in data:
            return jsonify({'error': 'Invalid subscription data'}), 400

        subscription_data = data['subscription']

        # Validate required fields
        required_fields = ['endpoint', 'keys']
        if not all(field in subscription_data for field in required_fields):
            return jsonify({'error': 'Missing required subscription fields'}), 400

        keys = subscription_data['keys']
        if 'p256dh' not in keys or 'auth' not in keys:
            return jsonify({'error': 'Missing encryption keys'}), 400

        # Check if subscription already exists
        existing_sub = PushSubscription.query.filter_by(
            user_id=current_user.id
        ).filter(
            PushSubscription.subscription_json.contains(subscription_data['endpoint'])
        ).first()

        if existing_sub:
            # Update existing subscription
            existing_sub.subscription_json = json.dumps(subscription_data)
            # Add these fields if they exist in your model
            if hasattr(existing_sub, 'user_agent'):
                existing_sub.user_agent = request.headers.get('User-Agent', '')
            if hasattr(existing_sub, 'is_active'):
                existing_sub.is_active = True
            if hasattr(existing_sub, 'last_used'):
                existing_sub.last_used = datetime.utcnow()
        else:
            # Create new subscription
            new_sub = PushSubscription(
                user_id=current_user.id,
                subscription_json=json.dumps(subscription_data)
            )

            # Add optional fields if they exist in your model
            if hasattr(new_sub, 'user_agent'):
                new_sub.user_agent = request.headers.get('User-Agent', '')
            if hasattr(new_sub, 'is_active'):
                new_sub.is_active = True

            db.session.add(new_sub)

        db.session.commit()

        # Create default notification preferences if they don't exist
        if not NotificationPreference.query.filter_by(user_id=current_user.id).first():
            prefs = NotificationPreference(user_id=current_user.id)
            db.session.add(prefs)
            db.session.commit()

        return jsonify({'message': 'Subscription saved successfully'}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to save subscription: {e}")
        return jsonify({'error': 'Failed to save subscription'}), 500


@push_bp.route('/unsubscribe', methods=['POST'])
@login_required
def unsubscribe():
    """Unsubscribe user from push notifications"""
    try:
        data = request.get_json()
        endpoint = data.get('endpoint') if data else None

        if endpoint:
            # Remove specific subscription by endpoint
            subscription = PushSubscription.query.filter_by(
                user_id=current_user.id
            ).filter(
                PushSubscription.subscription_json.contains(endpoint)
            ).first()

            if subscription:
                db.session.delete(subscription)
                message = 'Subscription removed successfully'
            else:
                message = 'Subscription not found'
        else:
            # Remove all subscriptions for user
            PushSubscription.query.filter_by(
                user_id=current_user.id
            ).delete()
            message = 'All subscriptions removed successfully'

        db.session.commit()
        return jsonify({'message': message}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to remove subscription: {e}")
        return jsonify({'error': 'Failed to remove subscription'}), 500


@push_bp.route('/test', methods=['POST'])
@login_required
def send_test_notification():
    """Send a test notification to current user"""
    try:
        data = request.get_json() or {}

        # Add debug logging
        current_app.logger.info(f"=== TEST NOTIFICATION DEBUG ===")
        current_app.logger.info(f"User ID: {current_user.id}")
        current_app.logger.info(f"Request data: {data}")

        # Check VAPID configuration
        vapid_private = current_app.config.get('VAPID_PRIVATE_KEY')
        vapid_public = current_app.config.get('VAPID_PUBLIC_KEY')
        vapid_email = current_app.config.get('VAPID_CLAIM_EMAIL')

        current_app.logger.info(f"VAPID private key exists: {bool(vapid_private)}")
        current_app.logger.info(f"VAPID private key length: {len(vapid_private) if vapid_private else 0}")
        current_app.logger.info(f"VAPID public key exists: {bool(vapid_public)}")
        current_app.logger.info(f"VAPID email: {vapid_email}")

        # Check subscriptions
        subscriptions = PushSubscription.query.filter_by(user_id=current_user.id).all()
        current_app.logger.info(f"Found {len(subscriptions)} subscriptions for user")

        for sub in subscriptions:
            current_app.logger.info(f"Subscription {sub.id}: endpoint={sub.get_endpoint()[:50]}...")

        result = push_service.send_notification_sync(
            user_ids=[current_user.id],
            notification_type='test',
            title=data.get('title', f'Hello {current_user.full_name}!'),
            body=data.get('body', 'This is a test notification from Fantasy Fairways'),
            url='/dashboard'
        )

        current_app.logger.info(f"Push service result: {result}")
        current_app.logger.info(f"=== END TEST NOTIFICATION DEBUG ===")

        return jsonify(result), 200

    except Exception as e:
        current_app.logger.error(f"Test notification exception: {str(e)}")
        import traceback
        current_app.logger.error(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@push_bp.route('/vapid-public-key', methods=['GET'])
def get_vapid_public_key():
    """Get VAPID public key for client-side subscription"""
    try:
        public_key = current_app.config.get('VAPID_PUBLIC_KEY')
        if not public_key:
            return jsonify({'error': 'VAPID public key not configured'}), 500

        return jsonify({'publicKey': public_key}), 200

    except Exception as e:
        current_app.logger.error(f"Failed to get VAPID public key: {e}")
        return jsonify({'error': 'Failed to get public key'}), 500


@push_bp.route('/preferences', methods=['GET', 'POST'])
@login_required
def notification_preferences():
    """Get or update user notification preferences"""
    if request.method == 'GET':
        # Get current preferences
        prefs = NotificationPreference.query.filter_by(user_id=current_user.id).first()

        if not prefs:
            # Create default preferences
            prefs = NotificationPreference(user_id=current_user.id)
            db.session.add(prefs)
            db.session.commit()

        return jsonify(prefs.to_dict()), 200

    elif request.method == 'POST':
        # Update preferences
        try:
            data = request.get_json()

            prefs = NotificationPreference.query.filter_by(user_id=current_user.id).first()
            if not prefs:
                prefs = NotificationPreference(user_id=current_user.id)
                db.session.add(prefs)

            # Update preferences
            for key, value in data.items():
                if hasattr(prefs, key) and isinstance(value, bool):
                    setattr(prefs, key, value)

            db.session.commit()
            return jsonify({'message': 'Preferences updated successfully'}), 200

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to update preferences: {e}")
            return jsonify({'error': 'Failed to update preferences'}), 500


# Analytics routes (called from service worker)
@push_bp.route('/analytics/notification-received', methods=['POST'])
def log_notification_received():
    """Log when a notification is received (called from service worker)"""
    try:
        data = request.get_json()
        current_app.logger.info(f"Notification received: {data}")
        return jsonify({'status': 'logged'}), 200

    except Exception as e:
        current_app.logger.error(f"Failed to log notification received: {e}")
        return jsonify({'error': 'Failed to log'}), 500


@push_bp.route('/analytics/notification-clicked', methods=['POST'])
def log_notification_clicked():
    """Log when a notification is clicked"""
    try:
        data = request.get_json()

        # Update notification log if we can find it
        if data.get('tag'):
            log_entry = NotificationLog.query.filter_by(
                notification_type=data.get('type'),
                status='sent'
            ).order_by(NotificationLog.sent_at.desc()).first()

            if log_entry:
                log_entry.clicked_at = datetime.utcnow()
                log_entry.status = 'clicked'
                db.session.commit()

        current_app.logger.info(f"Notification clicked: {data}")
        return jsonify({'status': 'logged'}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to log notification clicked: {e}")
        return jsonify({'error': 'Failed to log'}), 500


@push_bp.route('/analytics/notification-dismissed', methods=['POST'])
def log_notification_dismissed():
    """Log when a notification is dismissed"""
    try:
        data = request.get_json()

        if data.get('tag'):
            log_entry = NotificationLog.query.filter_by(
                notification_type=data.get('type'),
                status='sent'
            ).order_by(NotificationLog.sent_at.desc()).first()

            if log_entry:
                log_entry.dismissed_at = datetime.utcnow()
                log_entry.status = 'dismissed'
                db.session.commit()

        current_app.logger.info(f"Notification dismissed: {data}")
        return jsonify({'status': 'logged'}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to log notification dismissed: {e}")
        return jsonify({'error': 'Failed to log'}), 500


@push_bp.route('/stats', methods=['GET'])
@login_required
def get_notification_stats():
    """Get notification statistics (admin/user stats)"""
    try:
        if getattr(current_user, 'is_site_admin', False):
            # Admin stats - all notifications
            total_notifications = NotificationLog.query.count()
            successful_notifications = NotificationLog.query.filter_by(status='sent').count()
            total_subscriptions = PushSubscription.query.count()

            if hasattr(PushSubscription, 'is_active'):
                active_subscriptions = PushSubscription.query.filter_by(is_active=True).count()
            else:
                active_subscriptions = total_subscriptions

            stats = {
                'total_notifications': total_notifications,
                'successful_notifications': successful_notifications,
                'total_subscriptions': total_subscriptions,
                'active_subscriptions': active_subscriptions,
                'success_rate': round((successful_notifications / total_notifications * 100), 2) if total_notifications > 0 else 0
            }
        else:
            # User stats - their notifications only
            user_notifications = NotificationLog.query.filter_by(user_id=current_user.id).count()
            user_clicked = NotificationLog.query.filter_by(
                user_id=current_user.id,
                status='clicked'
            ).count()

            stats = {
                'notifications_received': user_notifications,
                'notifications_clicked': user_clicked,
                'click_rate': round((user_clicked / user_notifications * 100), 2) if user_notifications > 0 else 0
            }

        return jsonify(stats), 200

    except Exception as e:
        current_app.logger.error(f"Failed to get notification stats: {e}")
        return jsonify({'error': 'Failed to get stats'}), 500



# Add this to your push/routes.py temporarily
@push_bp.route('/debug-subscription', methods=['GET'])
@login_required
def debug_subscription():
    """Debug push subscription details"""
    try:
        # Get user's subscription
        subscription = PushSubscription.query.filter_by(user_id=current_user.id).first()

        if not subscription:
            return jsonify({'error': 'No subscription found for user'}), 404

        # Try to parse subscription
        subscription_data = subscription.to_dict()

        return jsonify({
            'subscription_exists': True,
            'subscription_endpoint': subscription_data.get('endpoint', 'Missing') if subscription_data else 'Invalid JSON',
            'has_keys': 'keys' in (subscription_data or {}),
            'vapid_configured': bool(current_app.config.get('VAPID_PRIVATE_KEY')),
            'vapid_claim_email': current_app.config.get('VAPID_CLAIM_EMAIL'),
            'subscription_raw': subscription.subscription_json[:100] + '...' if subscription.subscription_json else 'None'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500