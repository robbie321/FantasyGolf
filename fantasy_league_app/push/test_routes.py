# fantasy_league_app/push/test_routes.py
# Add this new file for comprehensive notification testing

from flask import Blueprint, request, jsonify, render_template_string, current_app
from flask_login import login_required, current_user
from fantasy_league_app.extensions import db
from fantasy_league_app.models import PushSubscription
from .services import push_service
import json

test_bp = Blueprint('push_test', __name__, url_prefix='/push-test')


@test_bp.route('/')
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
                }
            } catch (error) {
                log.error(`Error checking Service Worker: ${error.message}`);
            }

            return true;
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