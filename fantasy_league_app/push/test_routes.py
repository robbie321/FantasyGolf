from flask import Blueprint, request, jsonify, render_template_string, current_app, make_response
from flask_login import login_required, current_user
from fantasy_league_app.extensions import db, csrf
from fantasy_league_app.models import PushSubscription, User
from .services import push_service
import json
import base64

test_bp = Blueprint('push_test', __name__, url_prefix='/push-test')
test_bp.url_defaults({'_external': False})
# ===== EXEMPT CSRF FOR ALL PUSH ROUTES =====
csrf.exempt(test_bp)

@test_bp.route('/', strict_slashes=False)
@login_required
def test_dashboard():
    """Comprehensive push notification test dashboard"""

    # Get user's current subscriptions
    subscriptions = PushSubscription.query.filter_by(user_id=current_user.id).all()

    # Platform detection
    user_agent = request.headers.get('User-Agent', '')
    is_ios = 'iPhone' in user_agent or 'iPad' in user_agent
    is_android = 'Android' in user_agent
    is_safari = 'Safari' in user_agent and 'Chrome' not in user_agent

    html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Push Notification Test Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
        }

        .card {
            background: white;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }

        h1 {
            color: #2d3748;
            margin-bottom: 8px;
            font-size: 28px;
        }

        .subtitle {
            color: #718096;
            margin-bottom: 24px;
        }

        .status-badge {
            display: inline-block;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            margin-right: 8px;
        }

        .status-granted {
            background: #c6f6d5;
            color: #22543d;
        }

        .status-denied {
            background: #fed7d7;
            color: #742a2a;
        }

        .status-default {
            background: #feebc8;
            color: #744210;
        }

        .platform-info {
            background: #f7fafc;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 20px;
        }

        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e2e8f0;
        }

        .info-row:last-child {
            border-bottom: none;
        }

        .info-label {
            font-weight: 600;
            color: #4a5568;
        }

        .info-value {
            color: #718096;
            text-align: right;
        }

        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            margin-bottom: 12px;
            transition: all 0.3s ease;
        }

        .btn:hover {
            background: #5a67d8;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }

        .btn:disabled {
            background: #cbd5e0;
            cursor: not-allowed;
            transform: none;
        }

        .btn-danger {
            background: #f56565;
        }

        .btn-danger:hover {
            background: #e53e3e;
        }

        .log-container {
            background: #1a202c;
            color: #68d391;
            padding: 16px;
            border-radius: 8px;
            max-height: 400px;
            overflow-y: auto;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.6;
        }

        .log-entry {
            margin-bottom: 8px;
            padding-left: 20px;
            position: relative;
        }

        .log-entry:before {
            content: '→';
            position: absolute;
            left: 0;
            color: #667eea;
        }

        .log-success {
            color: #68d391;
        }

        .log-error {
            color: #fc8181;
        }

        .log-warning {
            color: #f6ad55;
        }

        .subscription-list {
            background: #f7fafc;
            padding: 16px;
            border-radius: 8px;
            margin-top: 16px;
        }

        .subscription-item {
            background: white;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 8px;
            font-size: 13px;
        }

        .subscription-endpoint {
            color: #718096;
            word-break: break-all;
            font-family: monospace;
            font-size: 11px;
        }

        .ios-warning {
            background: #fef5e7;
            border-left: 4px solid #f39c12;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 20px;
        }

        .ios-warning h3 {
            color: #d68910;
            margin-bottom: 8px;
        }

        .ios-steps {
            margin-left: 20px;
            color: #555;
        }

        .ios-steps li {
            margin-bottom: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>🔔 Push Notification Test Dashboard</h1>
            <p class="subtitle">Comprehensive testing for {{ current_user.full_name }}</p>

            <div class="platform-info">
                <div class="info-row">
                    <span class="info-label">Platform</span>
                    <span class="info-value" id="platform-info">Detecting...</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Browser</span>
                    <span class="info-value" id="browser-info">Detecting...</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Permission Status</span>
                    <span class="info-value" id="permission-status">
                        <span class="status-badge status-default">Checking...</span>
                    </span>
                </div>
                <div class="info-row">
                    <span class="info-label">Service Worker</span>
                    <span class="info-value" id="sw-status">Checking...</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Push Manager</span>
                    <span class="info-value" id="pm-status">Checking...</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Subscription Status</span>
                    <span class="info-value" id="sub-status">Checking...</span>
                </div>
            </div>

            {% if is_ios %}
            <div class="ios-warning">
                <h3>📱 iOS Safari Detected</h3>
                <p><strong>Important iOS Requirements:</strong></p>
                <ol class="ios-steps">
                    <li>Must add site to Home Screen first ("Add to Home Screen")</li>
                    <li>Open the app from the Home Screen icon (not Safari)</li>
                    <li>Then enable notifications</li>
                    <li>iOS requires HTTPS (localhost exempt in development)</li>
                </ol>
            </div>
            {% endif %}

            <div id="action-buttons">
                <button class="btn" id="check-support-btn" onclick="checkSupport()">
                    1️⃣ Check Browser Support
                </button>
                <button class="btn" id="register-sw-btn" onclick="registerServiceWorker()">
                    📝 Register Service Worker
                </button>
                <button class="btn" id="request-permission-btn" onclick="requestPermission()">
                    2️⃣ Request Permission
                </button>
                <button class="btn" id="subscribe-btn" onclick="subscribeToPush()">
                    3️⃣ Subscribe to Push
                </button>
                <button class="btn" id="test-notification-btn" onclick="sendTestNotification()">
                    4️⃣ Send Test Notification
                </button>
                <button class="btn btn-danger" id="unsubscribe-btn" onclick="unsubscribe()">
                    ❌ Unsubscribe
                </button>
            </div>

            <div class="subscription-list">
                <h3 style="margin-bottom: 12px; color: #2d3748;">Current Subscriptions ({{ subscriptions|length }})</h3>
                {% if subscriptions %}
                    {% for sub in subscriptions %}
                    <div class="subscription-item">
                        <div><strong>ID:</strong> {{ sub.id }}</div>
                        <div class="subscription-endpoint">
                            <strong>Endpoint:</strong> {{ sub.get_endpoint()[:80] }}...
                        </div>
                    </div>
                    {% endfor %}
                {% else %}
                    <p style="color: #718096; text-align: center;">No subscriptions yet</p>
                {% endif %}
            </div>
        </div>

        <div class="card">
            <h2 style="margin-bottom: 16px; color: #2d3748;">📋 Debug Log</h2>
            <div class="log-container" id="debug-log">
                <div class="log-entry">Waiting for actions...</div>
            </div>
            <button class="btn" onclick="clearLog()" style="margin-top: 12px;">Clear Log</button>
        </div>
    </div>

    <script>
        const log = {
            success: (msg) => addLog(msg, 'success'),
            error: (msg) => addLog(msg, 'error'),
            warning: (msg) => addLog(msg, 'warning'),
            info: (msg) => addLog(msg, 'info')
        };

        function addLog(message, type = 'info') {
            const logContainer = document.getElementById('debug-log');
            const entry = document.createElement('div');
            entry.className = `log-entry log-${type}`;
            entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
            logContainer.appendChild(entry);
            logContainer.scrollTop = logContainer.scrollHeight;
        }

        function clearLog() {
            document.getElementById('debug-log').innerHTML = '<div class="log-entry">Log cleared</div>';
        }

        function updateStatus(elementId, content) {
            document.getElementById(elementId).innerHTML = content;
        }

        async function detectPlatform() {
            const ua = navigator.userAgent;
            const isIOS = /iPad|iPhone|iPod/.test(ua);
            const isAndroid = /Android/.test(ua);
            const isMac = /Macintosh/.test(ua);
            const isWindows = /Windows/.test(ua);

            const isSafari = /Safari/.test(ua) && !/Chrome/.test(ua);
            const isChrome = /Chrome/.test(ua);
            const isFirefox = /Firefox/.test(ua);

            let platform = 'Unknown';
            if (isIOS) platform = 'iOS';
            else if (isAndroid) platform = 'Android';
            else if (isMac) platform = 'macOS';
            else if (isWindows) platform = 'Windows';

            let browser = 'Unknown';
            if (isSafari) browser = 'Safari';
            else if (isChrome) browser = 'Chrome';
            else if (isFirefox) browser = 'Firefox';

            updateStatus('platform-info', platform);
            updateStatus('browser-info', browser);

            log.info(`Platform: ${platform}, Browser: ${browser}`);

            // Check if standalone mode (PWA) on iOS
            if (isIOS && window.navigator.standalone) {
                log.success('Running as standalone PWA on iOS ✅');
            } else if (isIOS && !window.navigator.standalone) {
                log.warning('Not running as standalone PWA on iOS - notifications may not work');
            }
        }

        async function checkSupport() {
            log.info('Checking browser support...');

            // Check Notification API
            if (!('Notification' in window)) {
                log.error('❌ Notification API not supported');
                updateStatus('permission-status', '<span class="status-badge status-denied">Not Supported</span>');
                return false;
            }
            log.success('✅ Notification API supported');

            // Check Service Worker
            if (!('serviceWorker' in navigator)) {
                log.error('❌ Service Workers not supported');
                updateStatus('sw-status', '❌ Not Supported');
                return false;
            }
            log.success('✅ Service Workers supported');
            updateStatus('sw-status', '✅ Supported');

            // Check Push Manager
            if (!('PushManager' in window)) {
                log.error('❌ Push API not supported');
                updateStatus('pm-status', '❌ Not Supported');
                return false;
            }
            log.success('✅ Push API supported');
            updateStatus('pm-status', '✅ Supported');

            // Check current permission
            const permission = Notification.permission;
            log.info(`Current permission: ${permission}`);
            updatePermissionStatus(permission);

            // Check Service Worker registration
            try {
                const registration = await navigator.serviceWorker.getRegistration();
                if (registration) {
                    log.success('✅ Service Worker registered');
                    log.info(`SW scope: ${registration.scope}`);
                    log.info(`SW state: ${registration.active ? registration.active.state : 'no active worker'}`);

                    // Check subscription
                    const subscription = await registration.pushManager.getSubscription();
                    if (subscription) {
                        log.success('✅ Push subscription exists');
                        updateStatus('sub-status', '✅ Subscribed');
                    } else {
                        log.warning('⚠️ No push subscription found');
                        updateStatus('sub-status', '❌ Not Subscribed');
                    }
                } else {
                    log.warning('⚠️ Service Worker not registered yet');
                    updateStatus('sw-status', '⚠️ Not Registered');
                    log.info('👉 Click "Register Service Worker" button to register it');
                }
            } catch (error) {
                log.error(`Error checking Service Worker: ${error.message}`);
            }

            return true;
        }

        async function registerServiceWorker() {
            log.info('=== REGISTERING SERVICE WORKER ===');

            if (!('serviceWorker' in navigator)) {
                log.error('❌ Service Workers not supported in this browser');
                return false;
            }

            try {
                // Check if already registered
                let registration = await navigator.serviceWorker.getRegistration();

                if (registration) {
                    log.warning('Service Worker already registered');
                    log.info(`Scope: ${registration.scope}`);
                    log.info(`State: ${registration.active ? registration.active.state : 'unknown'}`);

                    // Check if it's active
                    if (registration.active && registration.active.state === 'activated') {
                        log.success('✅ Service Worker is active and ready');
                        updateStatus('sw-status', '✅ Registered & Active');
                        return true;
                    }

                    // If not active, try to update it
                    log.info('Updating Service Worker...');
                    await registration.update();
                    await navigator.serviceWorker.ready;
                    log.success('✅ Service Worker updated and ready');
                    updateStatus('sw-status', '✅ Registered & Active');
                    return true;
                }

                // Not registered yet, register it
                log.info('Registering new Service Worker...');

                // Serve from root to allow root scope
                const timestamp = new Date().getTime();
                const swUrl = '/service-worker.js?v=' + timestamp;

                log.info(`Looking for service worker at: ${swUrl}`);

                registration = await navigator.serviceWorker.register(swUrl, {
                    scope: '/',
                    updateViaCache: 'none'
                });

                log.success('✅ Service Worker registered!');
                log.info(`Scope: ${registration.scope}`);

                // Wait for it to be ready
                log.info('Waiting for Service Worker to activate...');
                await navigator.serviceWorker.ready;

                log.success('✅ Service Worker is now active and ready!');
                updateStatus('sw-status', '✅ Registered & Active');

                // Check final state
                const finalReg = await navigator.serviceWorker.getRegistration();
                if (finalReg && finalReg.active) {
                    log.info(`Final state: ${finalReg.active.state}`);
                }

                log.success('=== SERVICE WORKER REGISTRATION COMPLETE ===');
                return true;

            } catch (error) {
                log.error(`❌ Service Worker registration failed: ${error.message}`);
                log.error(`Error details: ${error.stack}`);

                // Try to provide helpful error messages
                if (error.message.includes('404')) {
                    log.error('📁 Service worker file not found at /static/js/service-worker.js');
                    log.info('Make sure the file exists and is accessible');
                } else if (error.message.includes('https')) {
                    log.error('🔒 HTTPS required for service workers (except on localhost)');
                } else if (error.message.includes('scope')) {
                    log.error('🔍 Scope issue - check service worker scope configuration');
                }

                updateStatus('sw-status', '❌ Registration Failed');
                return false;
            }
        }

        function updatePermissionStatus(permission) {
            let badgeClass, badgeText;

            switch(permission) {
                case 'granted':
                    badgeClass = 'status-granted';
                    badgeText = 'Granted ✅';
                    break;
                case 'denied':
                    badgeClass = 'status-denied';
                    badgeText = 'Denied ❌';
                    break;
                default:
                    badgeClass = 'status-default';
                    badgeText = 'Default ⚠️';
            }

            updateStatus('permission-status', `<span class="status-badge ${badgeClass}">${badgeText}</span>`);
        }

        async function requestPermission() {
            log.info('Requesting notification permission...');

            try {
                const permission = await Notification.requestPermission();
                log.info(`Permission result: ${permission}`);
                updatePermissionStatus(permission);

                if (permission === 'granted') {
                    log.success('✅ Permission granted!');
                    return true;
                } else if (permission === 'denied') {
                    log.error('❌ Permission denied');
                    return false;
                } else {
                    log.warning('⚠️ Permission dismissed');
                    return false;
                }
            } catch (error) {
                log.error(`Error requesting permission: ${error.message}`);
                return false;
            }
        }

        async function subscribeToPush() {
            log.info('Starting push subscription process...');

            try {
                // Get VAPID public key
                log.info('Fetching VAPID public key...');
                const response = await fetch('/api/push/vapid-public-key');
                const data = await response.json();

                if (!data.publicKey) {
                    log.error('❌ No VAPID public key received');
                    return;
                }

                log.success(`✅ Got VAPID key: ${data.publicKey.substring(0, 20)}...`);

                // Get or register Service Worker
                log.info('Getting Service Worker registration...');
                let registration = await navigator.serviceWorker.getRegistration();

                if (!registration) {
                    log.warning('No registration found, registering Service Worker...');
                    registration = await navigator.serviceWorker.register('/static/js/service-worker.js');
                    log.success('✅ Service Worker registered');

                    // Wait for activation
                    await navigator.serviceWorker.ready;
                    log.success('✅ Service Worker ready');
                }

                // Check if already subscribed
                let subscription = await registration.pushManager.getSubscription();

                if (subscription) {
                    log.warning('Already subscribed, unsubscribing first...');
                    await subscription.unsubscribe();
                }

                // Convert VAPID key
                const vapidPublicKey = urlBase64ToUint8Array(data.publicKey);
                log.info('VAPID key converted to Uint8Array');

                // Subscribe
                log.info('Creating push subscription...');
                subscription = await registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: vapidPublicKey
                });

                log.success('✅ Push subscription created!');
                log.info(`Endpoint: ${subscription.endpoint.substring(0, 50)}...`);

                // Send to server
                log.info('Sending subscription to server...');
                const saveResponse = await fetch('/api/push/subscribe', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        subscription: subscription.toJSON()
                    })
                });

                if (saveResponse.ok) {
                    log.success('✅ Subscription saved to server!');
                    updateStatus('sub-status', '✅ Subscribed');

                    // Refresh page to show new subscription
                    setTimeout(() => {
                        log.info('Refreshing page...');
                        location.reload();
                    }, 2000);
                } else {
                    const errorText = await saveResponse.text();
                    log.error(`❌ Failed to save subscription: ${errorText}`);
                }

            } catch (error) {
                log.error(`❌ Subscription failed: ${error.message}`);
                console.error('Full error:', error);
            }
        }

        async function sendTestNotification() {
            log.info('Sending test notification...');

            try {
                const response = await fetch('/api/push/test', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        title: 'Test Notification 🎉',
                        body: 'If you see this, push notifications are working!'
                    })
                });

                const result = await response.json();

                if (response.ok) {
                    log.success(`✅ Test notification sent! Success: ${result.success}, Failed: ${result.failed}`);

                    if (result.success > 0) {
                        log.success('Check your device for the notification!');
                    } else {
                        log.error('Notification was sent but may have failed. Check server logs.');
                    }
                } else {
                    log.error(`❌ Failed: ${result.error || 'Unknown error'}`);
                }

            } catch (error) {
                log.error(`❌ Request failed: ${error.message}`);
            }
        }

        async function unsubscribe() {
            log.info('Unsubscribing from push notifications...');

            try {
                const registration = await navigator.serviceWorker.getRegistration();
                if (!registration) {
                    log.warning('No Service Worker registration found');
                    return;
                }

                const subscription = await registration.pushManager.getSubscription();
                if (!subscription) {
                    log.warning('No subscription found');
                    return;
                }

                // Unsubscribe from push
                await subscription.unsubscribe();
                log.success('✅ Unsubscribed from push');

                // Remove from server
                const response = await fetch('/api/push/unsubscribe', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        endpoint: subscription.endpoint
                    })
                });

                if (response.ok) {
                    log.success('✅ Subscription removed from server');
                    updateStatus('sub-status', '❌ Not Subscribed');

                    setTimeout(() => {
                        location.reload();
                    }, 2000);
                }

            } catch (error) {
                log.error(`❌ Unsubscribe failed: ${error.message}`);
            }
        }

        function urlBase64ToUint8Array(base64String) {
            const padding = '='.repeat((4 - base64String.length % 4) % 4);
            const base64 = (base64String + padding)
                .replace(/\\-/g, '+')
                .replace(/_/g, '/');

            const rawData = window.atob(base64);
            const outputArray = new Uint8Array(rawData.length);

            for (let i = 0; i < rawData.length; ++i) {
                outputArray[i] = rawData.charCodeAt(i);
            }
            return outputArray;
        }

        // Initialize on load
        window.addEventListener('load', async () => {
            await detectPlatform();
            await checkSupport();
        });
    </script>
</body>
</html>
    '''

    return render_template_string(html,
                                 current_user=current_user,
                                 subscriptions=subscriptions,
                                 is_ios=is_ios,
                                 is_android=is_android,
                                 is_safari=is_safari)


@test_bp.route('/api/check-config')
@login_required
def check_config():
    """API endpoint to check server-side configuration"""

    vapid_private = current_app.config.get('VAPID_PRIVATE_KEY')
    vapid_public = current_app.config.get('VAPID_PUBLIC_KEY')
    vapid_email = current_app.config.get('VAPID_CLAIM_EMAIL')

    return jsonify({
        'vapid_configured': bool(vapid_private and vapid_public and vapid_email),
        'vapid_private_length': len(vapid_private) if vapid_private else 0,
        'vapid_public_length': len(vapid_public) if vapid_public else 0,
        'vapid_email': vapid_email,
        'vapid_public_preview': vapid_public[:20] + '...' if vapid_public else None,
        'redis_configured': bool(current_app.config.get('REDIS_URL')),
        'mail_configured': bool(current_app.config.get('MAIL_SERVER')),
        'environment': 'production' if not current_app.debug else 'development'
    })


@test_bp.route('/api/subscriptions')
@login_required
def list_subscriptions():
    """List all subscriptions for current user"""

    subscriptions = PushSubscription.query.filter_by(user_id=current_user.id).all()

    sub_list = []
    for sub in subscriptions:
        sub_data = sub.to_dict()
        sub_list.append({
            'id': sub.id,
            'endpoint': sub.get_endpoint()[:80] + '...' if hasattr(sub, 'get_endpoint') else 'N/A',
            'created_at': sub.created_at.isoformat() if hasattr(sub, 'created_at') else None,
            'is_active': sub.is_active if hasattr(sub, 'is_active') else True,
            'has_valid_data': bool(sub_data)
        })

    return jsonify({
        'count': len(subscriptions),
        'subscriptions': sub_list
    })


@test_bp.route('/api/send-custom', methods=['POST'])
@login_required
def send_custom_notification():
    """Send a custom notification for testing"""

    data = request.get_json()

    title = data.get('title', 'Test Notification')
    body = data.get('body', 'This is a test')
    url = data.get('url', '/')
    icon = data.get('icon')
    require_interaction = data.get('requireInteraction', False)

    result = push_service.send_notification_sync(
        user_ids=[current_user.id],
        notification_type='test',
        title=title,
        body=body,
        url=url,
        icon=icon,
        require_interaction=require_interaction
    )

    return jsonify(result)


@test_bp.route('/api/broadcast', methods=['POST'])
@login_required
def broadcast_test():
    """Broadcast notification to all users (admin only)"""

    # Check if user is admin
    if not getattr(current_user, 'is_site_admin', False):
        return jsonify({'error': 'Admin access required'}), 403

    data = request.get_json()

    # Get all active users
    all_users = User.query.filter_by(is_active=True).all()
    user_ids = [u.id for u in all_users]

    result = push_service.send_notification_sync(
        user_ids=user_ids,
        notification_type='broadcast',
        title=data.get('title', 'Broadcast Test'),
        body=data.get('body', 'This is a broadcast test notification'),
        url=data.get('url', '/')
    )

    return jsonify(result)


# In test_routes.py
@test_bp.route('/api/clear-subscriptions', methods=['POST'])
@login_required
def clear_subscriptions():
    """Clear all subscriptions for current user (for testing)"""

    try:
        # First, delete or update related notification logs
        from fantasy_league_app.push.models import NotificationLog

        # Get subscription IDs for this user
        subscription_ids = [sub.id for sub in PushSubscription.query.filter_by(user_id=current_user.id).all()]

        # Option 1: Delete related logs
        NotificationLog.query.filter(NotificationLog.subscription_id.in_(subscription_ids)).delete(synchronize_session=False)

        # OR Option 2: Set subscription_id to NULL in logs (if your model allows it)
        # NotificationLog.query.filter(NotificationLog.subscription_id.in_(subscription_ids)).update(
        #     {NotificationLog.subscription_id: None}, synchronize_session=False
        # )

        # Now delete the subscriptions
        deleted = PushSubscription.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()

        return jsonify({
            'success': True,
            'deleted': deleted,
            'message': f'Deleted {deleted} subscription(s) and related logs'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Clear subscriptions error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@test_bp.route('/api/vapid-info')
@login_required
def vapid_info():
    """Get VAPID key information for debugging"""

    vapid_public = current_app.config.get('VAPID_PUBLIC_KEY')
    vapid_private = current_app.config.get('VAPID_PRIVATE_KEY')

    def analyze_key(key):
        if not key:
            return {'error': 'Key not configured'}

        try:
            # Try to decode as base64url
            missing_padding = len(key) % 4
            if missing_padding:
                key_padded = key + '=' * (4 - missing_padding)
            else:
                key_padded = key

            # Convert to standard base64
            standard_b64 = key_padded.replace('-', '+').replace('_', '/')

            try:
                decoded = base64.b64decode(standard_b64)
                return {
                    'format': 'base64url',
                    'length_encoded': len(key),
                    'length_decoded': len(decoded),
                    'is_valid': len(decoded) in [32, 65],  # 32 for private, 65 for public
                    'preview': key[:20] + '...'
                }
            except:
                # Try standard base64
                try:
                    decoded = base64.b64decode(key)
                    return {
                        'format': 'base64_standard',
                        'length_encoded': len(key),
                        'length_decoded': len(decoded),
                        'is_valid': len(decoded) in [32, 65],
                        'preview': key[:20] + '...'
                    }
                except:
                    return {
                        'format': 'unknown',
                        'length': len(key),
                        'error': 'Could not decode',
                        'preview': key[:20] + '...'
                    }
        except Exception as e:
            return {
                'error': str(e)
            }

    return jsonify({
        'public_key': analyze_key(vapid_public),
        'private_key': analyze_key(vapid_private),
        'vapid_email': current_app.config.get('VAPID_CLAIM_EMAIL'),
        'recommendation': 'Keys should be base64url format, 32 bytes for private, 65 bytes for public'
    })


@test_bp.route('/manifest.json')
def manifest():
    """Serve PWA manifest for testing"""

    manifest_data = {
        "name": "Fantasy Golf",
        "short_name": "Fantasy Golf",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#006a4e",
        "icons": [
            {
                "src": "/static/images/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/images/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    }

    response = make_response(jsonify(manifest_data))
    response.headers['Content-Type'] = 'application/manifest+json'
    return response


@test_bp.route('/help')
def help_page():
    """Show help and troubleshooting information"""

    html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Push Notification Help</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .card {
            background: white;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #006a4e;
            padding-bottom: 10px;
        }
        h2 {
            color: #006a4e;
            margin-top: 24px;
        }
        h3 {
            color: #555;
        }
        .warning {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 12px;
            margin: 16px 0;
        }
        .success {
            background: #d4edda;
            border-left: 4px solid #28a745;
            padding: 12px;
            margin: 16px 0;
        }
        .error {
            background: #f8d7da;
            border-left: 4px solid #dc3545;
            padding: 12px;
            margin: 16px 0;
        }
        code {
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }
        pre {
            background: #2d3748;
            color: #68d391;
            padding: 16px;
            border-radius: 6px;
            overflow-x: auto;
        }
        ul {
            margin-left: 20px;
        }
        li {
            margin: 8px 0;
        }
        .btn {
            display: inline-block;
            padding: 10px 20px;
            background: #006a4e;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            margin: 10px 10px 10px 0;
        }
        .btn:hover {
            background: #005a3e;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>🔔 Push Notification Help & Troubleshooting</h1>

        <div class="success">
            <strong>Quick Links:</strong><br>
            <a href="/push-test" class="btn">Test Dashboard</a>
            <a href="/push-test/api/check-config" class="btn">Check Config</a>
            <a href="/push-test/api/vapid-info" class="btn">VAPID Info</a>
        </div>
    </div>

    <div class="card">
        <h2>📱 iOS Setup (Most Common Issue)</h2>

        <div class="warning">
            <strong>⚠️ iOS ONLY works in PWA mode!</strong><br>
            Safari browser tab does NOT support push notifications.
        </div>

        <h3>Required Steps for iOS:</h3>
        <ol>
            <li><strong>Add to Home Screen:</strong>
                <ul>
                    <li>Open site in Safari</li>
                    <li>Tap Share button (box with arrow up)</li>
                    <li>Scroll down and tap "Add to Home Screen"</li>
                    <li>Tap "Add"</li>
                </ul>
            </li>
            <li><strong>Open from Home Screen:</strong>
                <ul>
                    <li>Close Safari completely</li>
                    <li>Find the app icon on your Home Screen</li>
                    <li>Tap to open (this runs in PWA mode)</li>
                </ul>
            </li>
            <li><strong>Enable Notifications:</strong>
                <ul>
                    <li>Now tap "Enable Notifications"</li>
                    <li>Tap "Allow" when prompted</li>
                </ul>
            </li>
        </ol>

        <div class="error">
            <strong>If permission was denied:</strong><br>
            Go to: Settings → Safari → [Your Site] → Allow Notifications
        </div>
    </div>

    <div class="card">
        <h2>🤖 Android Setup</h2>

        <h3>Chrome on Android:</h3>
        <ol>
            <li>Visit the site in Chrome</li>
            <li>Tap "Enable Notifications"</li>
            <li>Tap "Allow" in the permission dialog</li>
        </ol>

        <div class="warning">
            <strong>Note:</strong> Android works in both browser and PWA mode
        </div>
    </div>

    <div class="card">
        <h2>🔧 Common Issues & Solutions</h2>

        <h3>Issue: Button does nothing when clicked</h3>
        <ul>
            <li>✅ iOS: Ensure app is added to Home Screen and opened from there</li>
            <li>✅ Check browser console for errors (F12 or inspect)</li>
            <li>✅ Verify you're on HTTPS (or localhost)</li>
            <li>✅ Try clearing browser cache and reloading</li>
        </ul>

        <h3>Issue: Permission immediately denied</h3>
        <ul>
            <li>✅ You previously denied - need to reset in browser settings</li>
            <li>✅ iOS: Settings → Safari → [Site] → Notifications</li>
            <li>✅ Android: Site Settings → Notifications → Allow</li>
            <li>✅ Desktop: Browser settings → Privacy → Notifications</li>
        </ul>

        <h3>Issue: Subscription fails with error</h3>
        <ul>
            <li>✅ Check VAPID keys are configured correctly</li>
            <li>✅ Verify service worker is registered</li>
            <li>✅ Check server logs for backend errors</li>
            <li>✅ Try the test dashboard at <code>/push-test</code></li>
        </ul>

        <h3>Issue: Notifications not received</h3>
        <ul>
            <li>✅ Verify subscription saved (check test dashboard)</li>
            <li>✅ Send test notification from <code>/push-test</code></li>
            <li>✅ Check device notification settings</li>
            <li>✅ Ensure device has internet connection</li>
            <li>✅ Check server logs for push delivery errors</li>
        </ul>
    </div>

    <div class="card">
        <h2>🔍 Debugging Steps</h2>

        <h3>1. Check Browser Support:</h3>
        <pre>console.log('Notification' in window);        // Should be true
console.log('serviceWorker' in navigator);   // Should be true
console.log('PushManager' in window);         // Should be true</pre>

        <h3>2. Check Permission Status:</h3>
        <pre>console.log(Notification.permission);        // granted, denied, or default</pre>

        <h3>3. Check Service Worker:</h3>
        <pre>navigator.serviceWorker.getRegistration().then(reg => {
    console.log('Registered:', !!reg);
    if (reg) console.log('Scope:', reg.scope);
});</pre>

        <h3>4. Check Subscription:</h3>
        <pre>navigator.serviceWorker.ready.then(reg => {
    return reg.pushManager.getSubscription();
}).then(sub => {
    console.log('Subscribed:', !!sub);
});</pre>

        <h3>5. Check Standalone Mode (iOS):</h3>
        <pre>console.log('Standalone:', window.navigator.standalone);
console.log('Display mode:', window.matchMedia('(display-mode: standalone)').matches);</pre>
    </div>

    <div class="card">
        <h2>⚙️ Server Configuration Checklist</h2>

        <ul>
            <li>✅ VAPID keys configured in base64url format (not DER)</li>
            <li>✅ VAPID_CLAIM_EMAIL set to valid mailto: URL</li>
            <li>✅ Service worker accessible at /static/js/service-worker.js</li>
            <li>✅ manifest.json accessible</li>
            <li>✅ HTTPS enabled (production only)</li>
            <li>✅ Push service properly initialized</li>
            <li>✅ Database models created (PushSubscription table exists)</li>
        </ul>

        <div class="success">
            <strong>Check server config:</strong><br>
            Visit <a href="/push-test/api/check-config">/push-test/api/check-config</a> for detailed info
        </div>
    </div>

    <div class="card">
        <h2>📚 Additional Resources</h2>

        <ul>
            <li><a href="https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/" target="_blank">Apple's Web Push Guide</a></li>
            <li><a href="https://developer.mozilla.org/en-US/docs/Web/API/Push_API" target="_blank">MDN Push API Documentation</a></li>
            <li><a href="https://web.dev/push-notifications-overview/" target="_blank">Web.dev Push Notifications Guide</a></li>
        </ul>
    </div>
</body>
</html>
    '''

    return html