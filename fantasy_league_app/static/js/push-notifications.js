/**
 * Push Notifications Manager for Fantasy Fairways
 * Handles subscription, permission requests, and UI components
 */

class PushNotificationManager {
    constructor() {
        this.swRegistration = null;
        this.isSubscribed = false;
        this.applicationServerKey = null;
        this.subscription = null;

        this.init();
    }

    async init() {
        console.log('[Push] Initializing push notification manager...');

        // Check if service workers and push notifications are supported
        if (!('serviceWorker' in navigator)) {
            console.warn('[Push] Service Workers not supported');
            this.showUnsupportedMessage('Service Workers not supported in this browser');
            return;
        }

        if (!('PushManager' in window)) {
            console.warn('[Push] Push notifications not supported');
            this.showUnsupportedMessage('Push notifications not supported in this browser');
            return;
        }

        try {
            // Register service worker
            this.swRegistration = await navigator.serviceWorker.register('/service-worker.js');
            console.log('[Push] Service Worker registered:', this.swRegistration);

            // Get VAPID public key from server
            await this.getApplicationServerKey();

            // Check current subscription status
            await this.checkSubscriptionStatus();

            // Set up UI
            this.setupUI();

            // Listen for messages from service worker
            this.setupMessageListener();

        } catch (error) {
            console.error('[Push] Initialization failed:', error);
        }
    }

    async getApplicationServerKey() {
        try {
            const response = await fetch('/api/push/vapid-public-key');
            if (!response.ok) {
                throw new Error('Failed to get VAPID public key');
            }

            const data = await response.json();
            console.log('[Push] VAPID key from server:', data.publicKey);
            console.log('[Push] Key length:', data.publicKey.length);

            // Your key is base64url format, convert it directly
            this.applicationServerKey = this.urlBase64ToUint8Array(data.publicKey);
            console.log('[Push] VAPID public key converted successfully');
            console.log('[Push] Final key length:', this.applicationServerKey.length);

        } catch (error) {
            console.error('[Push] Failed to get application server key:', error);
            throw error;
        }
    }

    extractRawKeyFromDER(derBase64) {
        console.log('[Push] Extracting raw public key from DER format');

        try {
            // Decode base64
            const derBytes = window.atob(derBase64);
            const byteArray = Array.from(derBytes).map(c => c.charCodeAt(0));

            console.log('[Push] DER bytes length:', byteArray.length);

            // Find the uncompressed point marker (0x04)
            // In DER format, the actual public key starts with 0x04
            const pointStart = byteArray.indexOf(0x04);

            if (pointStart === -1) {
                throw new Error('Could not find uncompressed point marker in DER data');
            }

            console.log('[Push] Found uncompressed point at index:', pointStart);

            // Extract the 65-byte uncompressed point
            const rawKeyBytes = byteArray.slice(pointStart, pointStart + 65);

            if (rawKeyBytes.length !== 65) {
                throw new Error(`Invalid raw key length: ${rawKeyBytes.length} (expected 65)`);
            }

            if (rawKeyBytes[0] !== 0x04) {
                throw new Error(`Invalid key format: first byte is ${rawKeyBytes[0]} (expected 4)`);
            }

            console.log('[Push] Successfully extracted raw public key, length:', rawKeyBytes.length);
            return new Uint8Array(rawKeyBytes);

        } catch (error) {
            console.error('[Push] Failed to extract raw public key from DER:', error);
            throw new Error(`DER public key extraction failed: ${error.message}`);
        }
    }

    async debugVapidKey() {
        try {
            console.log('=== VAPID KEY DEBUG ===');

            const response = await fetch('/api/push/vapid-public-key');
            const data = await response.json();

            console.log('Server key:', data.publicKey);
            console.log('Key length:', data.publicKey.length);

            // Try the extraction
            const extractedKey = this.extractRawKeyFromDER(data.publicKey);
            console.log('Extracted key length:', extractedKey.length);
            console.log('First 10 bytes:', Array.from(extractedKey.slice(0, 10)));

            return extractedKey;

        } catch (error) {
            console.error('Debug failed:', error);
            return null;
        }
    }

    async checkSubscriptionStatus() {
        try {
            this.subscription = await this.swRegistration.pushManager.getSubscription();
            this.isSubscribed = !(this.subscription === null);

            console.log('[Push] Subscription status:', this.isSubscribed);

            if (this.isSubscribed) {
                console.log('[Push] Current subscription endpoint:', this.subscription.endpoint.substring(0, 50) + '...');

                // Verify subscription is still valid by checking keys
                const subData = this.subscription.toJSON();
                if (subData.keys && subData.keys.p256dh && subData.keys.auth) {
                    console.log('[Push] Subscription has valid keys');
                } else {
                    console.warn('[Push] Subscription missing encryption keys');
                }
            } else {
                console.log('[Push] No active subscription found');
            }

        } catch (error) {
            console.error('[Push] Failed to check subscription status:', error);
            this.isSubscribed = false;
        }
    }

    setupUI() {
        // Update notification permission UI
        this.updatePermissionStatus();

        // Set up push notification toggle
        this.setupPushToggle();

        // Set up test notification button
        this.setupTestButton();

        // Set up permission request UI
        this.setupPermissionUI();

        // Update subscription status display
        this.updateSubscriptionDisplay();
    }

    setupMessageListener() {
        // Listen for messages from service worker
        navigator.serviceWorker.addEventListener('message', event => {
            console.log('[Push] Message from service worker:', event.data);

            if (event.data.type === 'NAVIGATE') {
                // Handle navigation requests from notification clicks
                window.location.href = event.data.url;
            }
        });
    }

    updatePermissionStatus() {
        const permission = Notification.permission;
        const statusElements = document.querySelectorAll('.notification-permission-status');

        statusElements.forEach(element => {
            element.textContent = this.getPermissionStatusText(permission);
            element.className = `notification-permission-status permission-${permission}`;
        });

        // Show/hide relevant UI elements
        const permissionBlocked = document.querySelectorAll('.permission-blocked');
        const permissionGranted = document.querySelectorAll('.permission-granted');
        const permissionDefault = document.querySelectorAll('.permission-default');

        permissionBlocked.forEach(el => el.style.display = permission === 'denied' ? 'block' : 'none');
        permissionGranted.forEach(el => el.style.display = permission === 'granted' ? 'block' : 'none');
        permissionDefault.forEach(el => el.style.display = permission === 'default' ? 'block' : 'none');
    }

    setupPushToggle() {
        const toggles = document.querySelectorAll('.push-notification-toggle');

        toggles.forEach(toggle => {
            toggle.checked = this.isSubscribed;
            toggle.disabled = Notification.permission !== 'granted';

            toggle.addEventListener('change', async (e) => {
                const isEnabled = e.target.checked;

                try {
                    if (isEnabled) {
                        await this.subscribeToPush();
                    } else {
                        await this.unsubscribeFromPush();
                    }
                } catch (error) {
                    console.error('[Push] Toggle failed:', error);
                    // Revert toggle state
                    e.target.checked = this.isSubscribed;
                    this.showError('Failed to update notification settings');
                }
            });
        });
    }

    setupTestButton() {
        const testButtons = document.querySelectorAll('.test-notification-btn');

        testButtons.forEach(button => {
            button.disabled = !this.isSubscribed;

            button.addEventListener('click', async () => {
                try {
                    button.disabled = true;
                    button.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sending...';

                    await this.sendTestNotification();

                    button.innerHTML = '<i class="fa-solid fa-check"></i> Sent!';
                    setTimeout(() => {
                        button.innerHTML = '<i class="fa-solid fa-bell"></i> Send Test';
                        button.disabled = !this.isSubscribed;
                    }, 2000);

                } catch (error) {
                    console.error('[Push] Test notification failed:', error);
                    button.innerHTML = '<i class="fa-solid fa-exclamation-triangle"></i> Failed';
                    setTimeout(() => {
                        button.innerHTML = '<i class="fa-solid fa-bell"></i> Send Test';
                        button.disabled = !this.isSubscribed;
                    }, 2000);
                }
            });
        });
    }

    setupPermissionUI() {
        const requestButtons = document.querySelectorAll('.request-notification-permission');

        requestButtons.forEach(button => {
            button.addEventListener('click', async () => {
                try {
                    await this.requestPermission();
                } catch (error) {
                    console.error('[Push] Permission request failed:', error);
                }
            });
        });

        // Auto-show permission request modal on first visit
        if (Notification.permission === 'default' && !localStorage.getItem('notificationPermissionRequested')) {
            setTimeout(() => {
                this.showPermissionRequestModal();
            }, 3000); // Show after 3 seconds
        }
    }

    async requestPermission() {
        try {
            console.log('[Push] Requesting notification permission...');
            console.log('[Push] Current permission status:', Notification.permission);

            // Check if notifications are supported
            if (!('Notification' in window)) {
                throw new Error('This browser does not support notifications');
            }

            if (Notification.permission === 'granted') {
                console.log('[Push] Permission already granted, proceeding to subscription');
                this.showSuccess('Notifications already enabled! Setting up push notifications...');

                // Try to subscribe immediately
                setTimeout(async () => {
                    try {
                        await this.subscribeToPush();
                    } catch (subscribeError) {
                        console.error('[Push] Auto-subscribe failed:', subscribeError);
                        this.showError('Permission granted but subscription setup failed. Please try again.');
                    }
                }, 500);

                return;
            }

            if (Notification.permission === 'denied') {
                this.showError('Notifications are blocked. Please enable them in your browser settings and refresh the page.');
                return;
            }

            // Request permission
            console.log('[Push] Requesting permission...');
            const permission = await Notification.requestPermission();

            localStorage.setItem('notificationPermissionRequested', 'true');
            this.updatePermissionStatus();

            console.log('[Push] Permission result:', permission);

            if (permission === 'granted') {
                this.showSuccess('Notifications enabled! Setting up push notifications...');

                // Wait a moment then try to subscribe
                setTimeout(async () => {
                    try {
                        await this.subscribeToPush();
                    } catch (subscribeError) {
                        console.error('[Push] Auto-subscribe failed:', subscribeError);
                        this.showError('Permission granted but subscription failed. Please try the toggle manually.');
                    }
                }, 1000);

            } else if (permission === 'denied') {
                this.showError('Notifications blocked. You can enable them in your browser settings.');
            } else {
                console.log('[Push] Permission was dismissed by user');
                this.showError('Notification permission was not granted. Please try again if you want to receive updates.');
            }

        } catch (error) {
            console.error('[Push] Permission request failed:', error);
            this.showError('Failed to request notification permission: ' + error.message);
        }
    }

    async subscribeToPush() {
        try {
            console.log('[Push] Starting subscription process...');

            if (Notification.permission !== 'granted') {
                throw new Error('Notification permission not granted');
            }

            if (!this.applicationServerKey) {
                console.log('[Push] No application server key, fetching...');
                await this.getApplicationServerKey();
            }

            if (!this.applicationServerKey) {
                throw new Error('Could not obtain VAPID public key');
            }

            console.log('[Push] Subscribing to push notifications...');
            console.log('[Push] Using key with length:', this.applicationServerKey.length);

            const subscription = await this.swRegistration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.applicationServerKey
            });

            console.log('[Push] Push subscription created:', subscription);

            // Send subscription to server
            await this.sendSubscriptionToServer(subscription);

            this.subscription = subscription;
            this.isSubscribed = true;

            this.updateSubscriptionDisplay();
            this.updateUIAfterSubscription();

            this.showSuccess('Push notifications enabled successfully!');

        } catch (error) {
            console.error('[Push] Subscription failed:', error);

            // Provide more specific error messages
            let errorMessage = 'Failed to enable push notifications: ' + error.message;

            if (error.message.includes('not valid')) {
                errorMessage = 'Server configuration error. Please contact support.';
            } else if (error.message.includes('permission')) {
                errorMessage = 'Please allow notifications in your browser settings.';
            }

            this.showError(errorMessage);
            throw error;
        }
    }

    async unsubscribeFromPush() {
        try {
            if (!this.subscription) {
                console.log('[Push] No subscription to unsubscribe from');
                return;
            }

            console.log('[Push] Unsubscribing from push notifications...');

            // Unsubscribe from push manager
            await this.subscription.unsubscribe();

            // Remove subscription from server
            await this.removeSubscriptionFromServer(this.subscription);

            this.subscription = null;
            this.isSubscribed = false;

            this.updateSubscriptionDisplay();
            this.updateUIAfterSubscription();

            this.showSuccess('Push notifications disabled successfully!');

        } catch (error) {
            console.error('[Push] Unsubscription failed:', error);
            this.showError('Failed to disable push notifications: ' + error.message);
            throw error;
        }
    }

    async sendSubscriptionToServer(subscription) {
        try {
            const csrfToken = this.getCSRFToken();
            const response = await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    subscription: subscription.toJSON()
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to save subscription');
            }

            console.log('[Push] Subscription sent to server successfully');

        } catch (error) {
            console.error('[Push] Failed to send subscription to server:', error);
            throw error;
        }
    }

    async removeSubscriptionFromServer(subscription) {
        try {
            const csrfToken = this.getCSRFToken();
            const response = await fetch('/api/push/unsubscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    endpoint: subscription.endpoint
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to remove subscription');
            }

            console.log('[Push] Subscription removed from server successfully');

        } catch (error) {
            console.error('[Push] Failed to remove subscription from server:', error);
            throw error;
        }
    }

    async sendTestNotification() {
        try {
            const csrfToken = this.getCSRFToken();
            const response = await fetch('/api/push/test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    title: 'Test Notification',
                    body: 'This is a test notification from Fantasy Fairways!'
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to send test notification');
            }

            console.log('[Push] Test notification sent successfully');

        } catch (error) {
            console.error('[Push] Failed to send test notification:', error);
            throw error;
        }
    }

    updateSubscriptionDisplay() {
        const subscriptionStatus = document.querySelectorAll('.subscription-status');

        subscriptionStatus.forEach(element => {
            element.textContent = this.isSubscribed ? 'Enabled' : 'Disabled';
            element.className = `subscription-status ${this.isSubscribed ? 'enabled' : 'disabled'}`;
        });
    }

    updateUIAfterSubscription() {
        // Update toggles
        const toggles = document.querySelectorAll('.push-notification-toggle');
        toggles.forEach(toggle => {
            toggle.checked = this.isSubscribed;
        });

        // Update test buttons
        const testButtons = document.querySelectorAll('.test-notification-btn');
        testButtons.forEach(button => {
            button.disabled = !this.isSubscribed;
        });
    }

    showPermissionRequestModal() {
        // Show permission request modal (you can implement this based on your UI needs)
        if (typeof showToast === 'function') {
            showToast('Enable notifications to get real-time updates about your fantasy teams!', 'info');
        }
    }

    // Utility functions
    urlBase64ToUint8Array(base64String) {
        console.log('[Push] Converting base64url key:', base64String);
        console.log('[Push] Original key length:', base64String.length);

        // Remove any whitespace
        base64String = base64String.replace(/\s/g, '');

        // Add padding if necessary for base64url
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const paddedKey = base64String + padding;

        // Convert base64url to regular base64
        const regularBase64 = paddedKey.replace(/-/g, '+').replace(/_/g, '/');

        console.log('[Push] Converting to regular base64:', regularBase64);

        try {
            const rawData = window.atob(regularBase64);
            console.log('[Push] Raw data length:', rawData.length);

            const outputArray = new Uint8Array(rawData.length);
            for (let i = 0; i < rawData.length; ++i) {
                outputArray[i] = rawData.charCodeAt(i);
            }

            console.log('[Push] Converted key length:', outputArray.length);

            // Validate the key
            if (outputArray.length === 65 && outputArray[0] === 0x04) {
                console.log('[Push] ✅ Valid P-256 uncompressed public key');
            } else if (outputArray.length === 65) {
                console.log('[Push] ⚠️ 65-byte key but unusual format (first byte:', outputArray[0], ')');
            } else {
                console.log('[Push] ⚠️ Unexpected key length:', outputArray.length, '(expected 65)');
            }

            console.log('[Push] Key conversion completed!');
            return outputArray;

        } catch (error) {
            console.error('[Push] Error converting VAPID key:', error);
            throw new Error('Invalid VAPID key format: ' + error.message);
        }
    }

    getCSRFToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    getPermissionStatusText(permission) {
        switch (permission) {
            case 'granted':
                return 'Enabled';
            case 'denied':
                return 'Blocked';
            case 'default':
                return 'Not requested';
            default:
                return 'Unknown';
        }
    }

    showSuccess(message) {
        if (typeof showToast === 'function') {
            showToast(message, 'success');
        } else {
            console.log('[Push] Success:', message);
        }
    }

    showError(message) {
        if (typeof showToast === 'function') {
            showToast(message, 'error');
        } else {
            console.error('[Push] Error:', message);
        }
    }

    showUnsupportedMessage(message) {
        console.warn('[Push] Unsupported:', message);
    }

    // Public methods for external use
    isNotificationSupported() {
        return 'serviceWorker' in navigator && 'PushManager' in window;
    }

    getPermissionStatus() {
        return Notification.permission;
    }

    getSubscriptionStatus() {
        return this.isSubscribed;
    }

    async testVapidKeyConversion() {
        try {
            console.log('[Push] Testing VAPID key conversion...');

            const response = await fetch('/api/push/vapid-public-key');
            if (!response.ok) {
                throw new Error('Failed to get VAPID public key');
            }

            const data = await response.json();
            console.log('[Push] Raw key from server:', data.publicKey);
            console.log('[Push] Key type:', typeof data.publicKey);
            console.log('[Push] Key length:', data.publicKey.length);

            // Test the conversion
            const convertedKey = this.urlBase64ToUint8Array(data.publicKey);
            console.log('[Push] Conversion test successful!');
            console.log('[Push] Converted key preview:', Array.from(convertedKey.slice(0, 10)));

            return convertedKey;

        } catch (error) {
            console.error('[Push] Key conversion test failed:', error);
            throw error;
        }
    }
}

function debugCurrentVapidKey() {
    // Your current key from config.py
    const currentKey = 'MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEMikeN4Y56qUl9NKtb6vvneJs+0BC7DfKXJlCQGCY23qRKl5uJS36c3SWJqVVvv6eo+5rvgnNOb8Rv1dUKcdEZQ==';

    console.log('=== VAPID KEY DEBUG ===');
    console.log('Current key from config:', currentKey);
    console.log('Key length:', currentKey.length);

    try {
        // Try to decode it
        const rawData = window.atob(currentKey);
        console.log('Decoded length:', rawData.length);
        console.log('First 10 bytes:', Array.from(rawData.slice(0, 10)).map(c => c.charCodeAt(0)));

        // Your key appears to be DER-encoded, not raw. Let's extract the raw key.
        // P-256 public keys in DER format have this structure:
        // 30 59 (SEQUENCE, 89 bytes)
        // 30 13 (SEQUENCE, 19 bytes) - algorithm identifier
        // ... algorithm stuff ...
        // 03 42 00 (BIT STRING, 66 bytes with 0 unused bits)
        // 04 ... (uncompressed point, 65 bytes)

        const bytes = Array.from(rawData).map(c => c.charCodeAt(0));
        console.log('All bytes:', bytes);

        // Look for the 0x04 byte that indicates start of uncompressed point
        const pointStart = bytes.indexOf(0x04);
        if (pointStart !== -1) {
            console.log('Found uncompressed point at index:', pointStart);
            const publicKeyBytes = bytes.slice(pointStart, pointStart + 65);
            console.log('Extracted public key length:', publicKeyBytes.length);
            console.log('Raw public key:', publicKeyBytes);

            // Convert to Uint8Array
            const publicKeyArray = new Uint8Array(publicKeyBytes);
            return publicKeyArray;
        } else {
            console.error('Could not find uncompressed point marker (0x04)');
        }

    } catch (error) {
        console.error('Failed to decode key:', error);
    }
}

// Initialize push notifications when DOM is ready
let pushManager = null;

document.addEventListener('DOMContentLoaded', async () => {
    console.log('[Push] Initializing push notification system...');

    try {
        // Initialize push manager
        pushManager = new PushNotificationManager();

        // Make push manager globally available
        window.pushManager = pushManager;

        console.log('[Push] Push notification system initialized successfully');

    } catch (error) {
        console.error('[Push] Failed to initialize push notification system:', error);
    }
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PushNotificationManager;
}
