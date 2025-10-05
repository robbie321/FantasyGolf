# fantasy_league_app/push/routes.py
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from fantasy_league_app.extensions import db, limiter, csrf
from fantasy_league_app.models import PushSubscription
from .models import NotificationLog, NotificationPreference
from .services import push_service

# Create blueprint
push_bp = Blueprint('push', __name__, url_prefix='/api/push')

# ===== EXEMPT CSRF FOR ALL PUSH ROUTES =====
csrf.exempt(push_bp)

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

        response = jsonify({'publicKey': public_key})

        # PREVENT CACHING
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

        return response, 200

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



@push_bp.route('/enable-log', methods=['POST'])
def log_enable_attempt():
    """Log notification enablement attempts for debugging and analytics"""
    try:
        data = request.get_json()

        # Extract data
        log_type = data.get('type', 'unknown')  # 'success' or 'error'
        timestamp = data.get('timestamp')
        user_agent = data.get('userAgent', '')
        is_ios = data.get('isIOS', False)
        is_standalone = data.get('isStandalone', False)
        details = data.get('details', {})

        # Get user if logged in
        user_id = current_user.id if current_user.is_authenticated else None

        # Log to application logger with structured data
        log_entry = {
            'type': log_type,
            'user_id': user_id,
            'timestamp': timestamp,
            'user_agent': user_agent,
            'is_ios': is_ios,
            'is_standalone': is_standalone,
            'completed_steps': details.get('completedSteps', []),
            'failed_step': details.get('failedStep'),
            'error': details.get('error'),
            'message': details.get('message')
        }

        if log_type == 'success':
            current_app.logger.info(f"[PUSH_ENABLE_SUCCESS] User {user_id}: {log_entry}")
        else:
            current_app.logger.error(f"[PUSH_ENABLE_ERROR] User {user_id}: {log_entry}")

        # Optionally save to database for analytics
        # You can create a new model for this or use NotificationLog
        try:
            notification_log = NotificationLog(
                user_id=user_id,
                notification_type='enable_attempt',
                title=f'Notification Enable: {log_type}',
                body=details.get('message', ''),
                data=json.dumps(log_entry),
                status='sent' if log_type == 'success' else 'failed',
                error_message=details.get('error') if log_type == 'error' else None,
                sent_at=datetime.utcnow()
            )
            db.session.add(notification_log)
            db.session.commit()
        except Exception as db_error:
            current_app.logger.error(f"Failed to save enable log to database: {db_error}")
            db.session.rollback()

        return jsonify({
            'status': 'logged',
            'message': 'Enable attempt logged successfully'
        }), 200

    except Exception as e:
        current_app.logger.error(f"Failed to log enable attempt: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to log enable attempt'
        }), 500


@push_bp.route('/check-status', methods=['GET'])
@login_required
def check_notification_status():
    """Check if user has active push subscription"""
    try:
        # Check if user has any active subscriptions
        subscription = PushSubscription.query.filter_by(
            user_id=current_user.id
        ).first()

        if hasattr(subscription, 'is_active'):
            has_subscription = subscription and subscription.is_active
        else:
            has_subscription = bool(subscription)

        return jsonify({
            'enabled': has_subscription,
            'subscription_count': PushSubscription.query.filter_by(
                user_id=current_user.id
            ).count(),
            'last_subscription': subscription.created_at.isoformat() if subscription and hasattr(subscription, 'created_at') else None
        }), 200

    except Exception as e:
        current_app.logger.error(f"Failed to check notification status: {e}")
        return jsonify({
            'enabled': False,
            'error': 'Failed to check status'
        }), 500


@push_bp.route('/troubleshoot', methods=['POST'])
@login_required
def troubleshoot_notifications():
    """Troubleshooting endpoint to help debug notification issues"""
    try:
        data = request.get_json() or {}

        # Collect diagnostic information
        diagnostics = {
            'user_id': current_user.id,
            'timestamp': datetime.utcnow().isoformat(),
            'user_agent': request.headers.get('User-Agent', ''),
            'reported_issue': data.get('issue', 'Unknown'),
            'browser_info': data.get('browserInfo', {}),
            'subscription_info': {}
        }

        # Check subscriptions
        subscriptions = PushSubscription.query.filter_by(
            user_id=current_user.id
        ).all()

        diagnostics['subscription_info'] = {
            'count': len(subscriptions),
            'subscriptions': []
        }

        for sub in subscriptions:
            sub_info = {
                'id': sub.id,
                'created': sub.created_at.isoformat() if hasattr(sub, 'created_at') else None,
                'is_active': sub.is_active if hasattr(sub, 'is_active') else True,
                'endpoint_preview': sub.get_endpoint()[:50] + '...' if hasattr(sub, 'get_endpoint') else 'N/A'
            }
            diagnostics['subscription_info']['subscriptions'].append(sub_info)

        # Check VAPID configuration
        diagnostics['vapid_configured'] = bool(
            current_app.config.get('VAPID_PRIVATE_KEY') and
            current_app.config.get('VAPID_PUBLIC_KEY') and
            current_app.config.get('VAPID_CLAIM_EMAIL')
        )

        # Log diagnostics
        current_app.logger.warning(f"[PUSH_TROUBLESHOOT] User {current_user.id}: {diagnostics}")

        # Save to database
        try:
            troubleshoot_log = NotificationLog(
                user_id=current_user.id,
                notification_type='troubleshoot',
                title='Notification Troubleshooting',
                body=data.get('issue', 'Unknown issue'),
                data=json.dumps(diagnostics),
                status='pending',
                sent_at=datetime.utcnow()
            )
            db.session.add(troubleshoot_log)
            db.session.commit()
        except Exception as db_error:
            current_app.logger.error(f"Failed to save troubleshoot log: {db_error}")
            db.session.rollback()

        return jsonify({
            'status': 'received',
            'diagnostics': diagnostics,
            'suggestions': generate_suggestions(diagnostics)
        }), 200

    except Exception as e:
        current_app.logger.error(f"Troubleshoot endpoint error: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


def generate_suggestions(diagnostics):
    """Generate troubleshooting suggestions based on diagnostics"""
    suggestions = []

    # Check subscription count
    if diagnostics['subscription_info']['count'] == 0:
        suggestions.append({
            'issue': 'No active subscriptions',
            'suggestion': 'Try enabling notifications again using the button above'
        })

    # Check VAPID
    if not diagnostics.get('vapid_configured'):
        suggestions.append({
            'issue': 'Server configuration issue',
            'suggestion': 'VAPID keys not properly configured. Contact support.'
        })

    # Check multiple subscriptions
    if diagnostics['subscription_info']['count'] > 3:
        suggestions.append({
            'issue': 'Multiple subscriptions detected',
            'suggestion': 'Try disabling and re-enabling notifications to clean up old subscriptions'
        })

    # Check browser
    user_agent = diagnostics.get('user_agent', '').lower()
    if 'safari' in user_agent and 'chrome' not in user_agent:
        if 'iphone' in user_agent or 'ipad' in user_agent:
            suggestions.append({
                'issue': 'iOS Safari detected',
                'suggestion': 'Make sure the app is added to Home Screen and opened from there'
            })

    if not suggestions:
        suggestions.append({
            'issue': 'No specific issues detected',
            'suggestion': 'Your notifications appear to be configured correctly. Try sending a test notification.'
        })

    return suggestions