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
            this.applicationServerKey = this.urlBase64ToUint8Array(data.publicKey);
            console.log('[Push] VAPID public key retrieved');

        } catch (error) {
            console.error('[Push] Failed to get application server key:', error);
            throw error;
        }
    }

    async checkSubscriptionStatus() {
        try {
            this.subscription = await this.swRegistration.pushManager.getSubscription();
            this.isSubscribed = !(this.subscription === null);

            console.log('[Push] Subscription status:', this.isSubscribed);

            if (this.isSubscribed) {
                console.log('[Push] Current subscription:', this.subscription);
            }

        } catch (error) {
            console.error('[Push] Failed to check subscription status:', error);
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
            const permission = await Notification.requestPermission();

            localStorage.setItem('notificationPermissionRequested', 'true');

            this.updatePermissionStatus();

            if (permission === 'granted') {
                this.showSuccess('Notifications enabled! You can now receive updates.');

                // Automatically subscribe to push notifications
                await this.subscribeToPush();
            } else if (permission === 'denied') {
                this.showError('Notifications blocked. You can enable them in your browser settings.');
            }

        } catch (error) {
            console.error('[Push] Permission request failed:', error);
            this.showError('Failed to request notification permission');
        }
    }

    async subscribeToPush() {
        try {
            if (Notification.permission !== 'granted') {
                throw new Error('Notification permission not granted');
            }

            if (!this.applicationServerKey) {
                throw new Error('Application server key not available');
            }

            console.log('[Push] Subscribing to push notifications...');

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
            this.showError('Failed to enable push notifications: ' + error.message);
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
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');

        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);

        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }

        return outputArray;
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