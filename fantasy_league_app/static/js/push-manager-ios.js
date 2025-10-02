// static/js/push-manager-ios.js
// Enhanced push notification manager with full iOS support

class PushNotificationManager {
    constructor() {
        this.isSubscribed = false;
        this.subscription = null;
        this.vapidPublicKey = null;
        this.isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        this.isSafari = /Safari/.test(navigator.userAgent) && !/Chrome/.test(navigator.userAgent);
        this.isStandalone = window.navigator.standalone || window.matchMedia('(display-mode: standalone)').matches;

        console.log('🔔 Push Manager initialized', {
            isIOS: this.isIOS,
            isSafari: this.isSafari,
            isStandalone: this.isStandalone
        });
    }

    // Initialize the push manager
    async init() {
        console.log('🔔 Initializing push notifications...');

        // Check browser support
        if (!this.checkSupport()) {
            console.error('❌ Push notifications not supported');
            return false;
        }

        // iOS-specific checks
        if (this.isIOS) {
            if (!this.isStandalone) {
                console.warn('⚠️ iOS: App must be added to Home Screen for notifications');
                this.showIOSInstructions();
                return false;
            }
            console.log('✅ iOS: Running in standalone mode');
        }

        // Register service worker
        const registered = await this.registerServiceWorker();
        if (!registered) {
            console.error('❌ Service worker registration failed');
            return false;
        }

        // Get VAPID public key
        const gotKey = await this.getVapidPublicKey();
        if (!gotKey) {
            console.error('❌ Failed to get VAPID key');
            return false;
        }

        // Check current subscription status
        await this.checkSubscriptionStatus();

        console.log('✅ Push manager initialized successfully');
        return true;
    }

    // Check if push notifications are supported
    checkSupport() {
        const hasNotification = 'Notification' in window;
        const hasServiceWorker = 'serviceWorker' in navigator;
        const hasPushManager = 'PushManager' in window;

        console.log('Browser support:', {
            Notification: hasNotification,
            ServiceWorker: hasServiceWorker,
            PushManager: hasPushManager
        });

        if (!hasNotification) {
            console.error('❌ Notification API not supported');
            return false;
        }

        if (!hasServiceWorker) {
            console.error('❌ Service Workers not supported');
            return false;
        }

        if (!hasPushManager) {
            console.error('❌ Push Manager not supported');
            return false;
        }

        return true;
    }

    // Show iOS-specific instructions
    showIOSInstructions() {
        const message = `
To enable notifications on iOS:
1. Tap the Share button in Safari
2. Tap "Add to Home Screen"
3. Open the app from your Home Screen
4. Then enable notifications
        `.trim();

        console.log('📱 iOS Instructions:', message);

        // You can also show this in your UI
        if (typeof window.showNotificationPrompt === 'function') {
            window.showNotificationPrompt();
        }
    }

    // Register the service worker
    async registerServiceWorker() {
        try {
            console.log('📝 Registering service worker...');

            const swUrl = window.location.protocol === 'https:'
            ? `https://${window.location.host}/service-worker.js`
            : '/static/service-worker.js';

            const registration = await navigator.serviceWorker.register(
                '/service-worker.js',
                { scope: '/s', }
            );

            console.log('✅ Service worker registered:', registration.scope);

            // Wait for service worker to be ready
            await navigator.serviceWorker.ready;
            console.log('✅ Service worker ready');

            // Update on new service worker
            registration.addEventListener('updatefound', () => {
                console.log('🔄 New service worker found');
                const newWorker = registration.installing;

                newWorker.addEventListener('statechange', () => {
                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                        console.log('🔄 New service worker installed, refresh to update');
                        // Optionally prompt user to refresh
                    }
                });
            });

            return true;
        } catch (error) {
            console.error('❌ Service worker registration failed:', error);
            return false;
        }
    }

    // Get VAPID public key from server
    async getVapidPublicKey() {
        try {
            console.log('🔑 Fetching VAPID public key...');

            const response = await fetch('/api/push/vapid-public-key');
            const data = await response.json();

            if (!data.publicKey) {
                throw new Error('No VAPID public key in response');
            }

            this.vapidPublicKey = data.publicKey;
            console.log('✅ VAPID key received:', this.vapidPublicKey.substring(0, 20) + '...');

            return true;
        } catch (error) {
            console.error('❌ Failed to get VAPID key:', error);
            return false;
        }
    }

    // Check current subscription status
    async checkSubscriptionStatus() {
        try {
            const registration = await navigator.serviceWorker.ready;
            this.subscription = await registration.pushManager.getSubscription();

            if (this.subscription) {
                this.isSubscribed = true;
                console.log('✅ Already subscribed to push');
                console.log('📍 Endpoint:', this.subscription.endpoint.substring(0, 50) + '...');
            } else {
                this.isSubscribed = false;
                console.log('ℹ️ Not subscribed to push');
            }

            return this.isSubscribed;
        } catch (error) {
            console.error('❌ Error checking subscription:', error);
            return false;
        }
    }

    // Request notification permission
    async requestPermission() {
        console.log('🔔 Requesting notification permission...');

        try {
            // iOS requires the permission request to be triggered by user interaction
            const permission = await Notification.requestPermission();

            console.log('📋 Permission result:', permission);

            if (permission === 'granted') {
                console.log('✅ Permission granted');
                return true;
            } else if (permission === 'denied') {
                console.log('❌ Permission denied');
                this.showPermissionDeniedMessage();
                return false;
            } else {
                console.log('⚠️ Permission dismissed');
                return false;
            }
        } catch (error) {
            console.error('❌ Permission request failed:', error);
            return false;
        }
    }

    // Subscribe to push notifications
    async subscribe() {
        console.log('📝 Starting subscription process...');

        try {
            // Check permission first
            if (Notification.permission !== 'granted') {
                const permitted = await this.requestPermission();
                if (!permitted) {
                    throw new Error('Permission not granted');
                }
            }

            // Get service worker registration
            const registration = await navigator.serviceWorker.ready;
            console.log('✅ Service worker ready for subscription');

            // Check if already subscribed
            let subscription = await registration.pushManager.getSubscription();

            if (subscription) {
                console.log('⚠️ Already subscribed, unsubscribing first...');
                await subscription.unsubscribe();
                console.log('✅ Previous subscription removed');
            }

            // Convert VAPID key
            const applicationServerKey = this.urlBase64ToUint8Array(this.vapidPublicKey);
            console.log('🔑 VAPID key converted to Uint8Array');

            // Subscribe to push
            console.log('📡 Creating push subscription...');
            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: applicationServerKey
            });

            console.log('✅ Push subscription created!');
            console.log('📍 Endpoint:', subscription.endpoint.substring(0, 50) + '...');

            // Save subscription to server
            const saved = await this.saveSubscriptionToServer(subscription);

            if (saved) {
                this.subscription = subscription;
                this.isSubscribed = true;
                console.log('✅ Subscription saved successfully');
                return true;
            } else {
                throw new Error('Failed to save subscription to server');
            }

        } catch (error) {
            console.error('❌ Subscription failed:', error);
            this.showSubscriptionError(error);
            return false;
        }
    }

    // Save subscription to server
    async saveSubscriptionToServer(subscription) {
        try {
            console.log('💾 Saving subscription to server...');

            const response = await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    subscription: subscription.toJSON()
                })
            });

            if (response.ok) {
                console.log('✅ Subscription saved to server');
                return true;
            } else {
                const errorText = await response.text();
                console.error('❌ Server error:', errorText);
                return false;
            }
        } catch (error) {
            console.error('❌ Save to server failed:', error);
            return false;
        }
    }

    // Unsubscribe from push notifications
    async unsubscribe() {
        console.log('🔕 Unsubscribing from push...');

        try {
            if (!this.subscription) {
                const registration = await navigator.serviceWorker.ready;
                this.subscription = await registration.pushManager.getSubscription();
            }

            if (!this.subscription) {
                console.log('ℹ️ No subscription to remove');
                return true;
            }

            const endpoint = this.subscription.endpoint;

            // Unsubscribe from push
            await this.subscription.unsubscribe();
            console.log('✅ Unsubscribed from push');

            // Remove from server
            await fetch('/api/push/unsubscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ endpoint })
            });

            console.log('✅ Subscription removed from server');

            this.subscription = null;
            this.isSubscribed = false;

            return true;
        } catch (error) {
            console.error('❌ Unsubscribe failed:', error);
            return false;
        }
    }

    // Send a test notification
    async sendTestNotification() {
        console.log('🧪 Sending test notification...');

        try {
            const response = await fetch('/api/push/test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    title: 'Test Notification 🎉',
                    body: 'If you see this, push notifications are working perfectly!'
                })
            });

            const result = await response.json();

            if (response.ok) {
                console.log('✅ Test notification sent:', result);
                return true;
            } else {
                console.error('❌ Test notification failed:', result);
                return false;
            }
        } catch (error) {
            console.error('❌ Test notification request failed:', error);
            return false;
        }
    }

    // Helper: Convert VAPID key from base64 to Uint8Array
    urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/\-/g, '+')
            .replace(/_/g, '/');

        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);

        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    // Show error messages
    showPermissionDeniedMessage() {
        console.log('⚠️ To enable notifications:');

        if (this.isIOS) {
            console.log('iOS: Go to Settings > Safari > this website > Allow Notifications');
        } else {
            console.log('Go to browser settings and allow notifications for this site');
        }
    }

    showSubscriptionError(error) {
        console.error('Subscription error details:', {
            message: error.message,
            name: error.name,
            stack: error.stack
        });
    }

    // Get current subscription state
    getState() {
        return {
            isSupported: this.checkSupport(),
            isSubscribed: this.isSubscribed,
            permission: Notification.permission,
            isIOS: this.isIOS,
            isStandalone: this.isStandalone,
            hasSubscription: !!this.subscription
        };
    }
}

// Create global instance
window.pushManager = new PushNotificationManager();

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.pushManager.init();
    });
} else {
    window.pushManager.init();
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PushNotificationManager;
}