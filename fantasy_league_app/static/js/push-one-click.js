// static/js/push-one-click.js
// Single-button push notification enabler with comprehensive error handling

class OneClickPushManager {
    constructor() {
        this.isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
        this.isStandalone = window.navigator.standalone || window.matchMedia('(display-mode: standalone)').matches;
        this.steps = [];
        this.currentStep = 0;
    }

    /**
     * Main method - enables notifications with one click
     * @returns {Promise<Object>} Result object with success status and details
     */
    async enableNotifications() {
        this.steps = [];
        this.currentStep = 0;

        const result = {
            success: false,
            completedSteps: [],
            failedStep: null,
            error: null,
            message: ''
        };

        try {
            // Step 1: Check browser support
            await this.logStep('Checking browser support');
            const supportCheck = this.checkSupport();
            if (!supportCheck.supported) {
                throw new Error(supportCheck.reason);
            }
            result.completedSteps.push('Browser support verified');

            // Step 2: iOS-specific validation
            if (this.isIOS) {
                await this.logStep('Validating iOS requirements');
                if (!this.isStandalone) {
                    throw new Error('iOS_STANDALONE_REQUIRED');
                }
                result.completedSteps.push('iOS standalone mode verified');
            }

            // Step 3: Register service worker
            await this.logStep('Registering service worker');
            const registration = await this.registerServiceWorker();
            result.completedSteps.push('Service worker registered');

            // Step 4: Request notification permission
            await this.logStep('Requesting notification permission');
            const permission = await this.requestPermission();
            if (permission !== 'granted') {
                throw new Error('PERMISSION_DENIED');
            }
            result.completedSteps.push('Notification permission granted');

            // Step 5: Get VAPID key
            await this.logStep('Fetching VAPID key');
            const vapidKey = await this.getVapidPublicKey();
            result.completedSteps.push('VAPID key retrieved');

            // Step 6: Subscribe to push
            await this.logStep('Creating push subscription');
            const subscription = await this.subscribeToPush(registration, vapidKey);
            result.completedSteps.push('Push subscription created');

            // Step 7: Save to server
            await this.logStep('Saving subscription to server');
            await this.saveSubscriptionToServer(subscription);
            result.completedSteps.push('Subscription saved to server');

            // Success!
            result.success = true;
            result.message = 'Notifications enabled successfully!';

            // Log success to server
            await this.logToServer('success', result);

            return result;

        } catch (error) {
            result.success = false;
            result.failedStep = this.steps[this.currentStep] || 'Unknown step';
            result.error = error.message;
            result.message = this.getErrorMessage(error);

            // Log failure to server
            await this.logToServer('error', result);

            return result;
        }
    }

    /**
     * Check if browser supports all required features
     */
    checkSupport() {
        if (!('Notification' in window)) {
            return { supported: false, reason: 'NOTIFICATION_API_UNSUPPORTED' };
        }

        if (!('serviceWorker' in navigator)) {
            return { supported: false, reason: 'SERVICE_WORKER_UNSUPPORTED' };
        }

        if (!('PushManager' in window)) {
            return { supported: false, reason: 'PUSH_MANAGER_UNSUPPORTED' };
        }

        return { supported: true };
    }

    /**
     * Register service worker
     */
    async registerServiceWorker() {
        try {
            // Check if already registered
            let registration = await navigator.serviceWorker.getRegistration();

            if (registration) {
                console.log('[OneClick] Service worker already registered');
                await navigator.serviceWorker.ready;
                return registration;
            }

            // Register new service worker
            const timestamp = new Date().getTime();
            registration = await navigator.serviceWorker.register(
                `/service-worker.js?v=${timestamp}`,
                { scope: '/', updateViaCache: 'none' }
            );

            // Wait for it to be ready
            await navigator.serviceWorker.ready;

            return registration;

        } catch (error) {
            console.error('[OneClick] Service worker registration failed:', error);
            throw new Error('SERVICE_WORKER_REGISTRATION_FAILED');
        }
    }

    /**
     * Request notification permission
     */
    async requestPermission() {
        try {
            const permission = await Notification.requestPermission();
            return permission;
        } catch (error) {
            console.error('[OneClick] Permission request failed:', error);
            throw new Error('PERMISSION_REQUEST_FAILED');
        }
    }

    /**
     * Get VAPID public key from server
     */
    async getVapidPublicKey() {
        try {
            const response = await fetch('/api/push/vapid-public-key');

            if (!response.ok) {
                throw new Error('Server returned error');
            }

            const data = await response.json();

            if (!data.publicKey) {
                throw new Error('No public key in response');
            }

            return data.publicKey;

        } catch (error) {
            console.error('[OneClick] VAPID key fetch failed:', error);
            throw new Error('VAPID_KEY_FETCH_FAILED');
        }
    }

    /**
     * Subscribe to push notifications
     */
    async subscribeToPush(registration, vapidPublicKey) {
        try {
            // Check for existing subscription
            let subscription = await registration.pushManager.getSubscription();

            if (subscription) {
                console.log('[OneClick] Unsubscribing from existing subscription');
                await subscription.unsubscribe();
            }

            // Convert VAPID key
            const applicationServerKey = this.urlBase64ToUint8Array(vapidPublicKey);

            // Create new subscription
            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: applicationServerKey
            });

            return subscription;

        } catch (error) {
            console.error('[OneClick] Push subscription failed:', error);
            throw new Error('PUSH_SUBSCRIPTION_FAILED');
        }
    }

    /**
     * Save subscription to server
     */
    async saveSubscriptionToServer(subscription) {
        try {
            const response = await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    subscription: subscription.toJSON()
                })
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Server error: ${errorText}`);
            }

            return true;

        } catch (error) {
            console.error('[OneClick] Save to server failed:', error);
            throw new Error('SERVER_SAVE_FAILED');
        }
    }

    /**
     * Get user-friendly error message
     */
    getErrorMessage(error) {
        const errorMessages = {
            'NOTIFICATION_API_UNSUPPORTED': 'Your browser doesn\'t support notifications.',
            'SERVICE_WORKER_UNSUPPORTED': 'Your browser doesn\'t support service workers.',
            'PUSH_MANAGER_UNSUPPORTED': 'Your browser doesn\'t support push notifications.',
            'iOS_STANDALONE_REQUIRED': 'On iOS, please add this app to your Home Screen first, then open it from there to enable notifications.',
            'SERVICE_WORKER_REGISTRATION_FAILED': 'Failed to register service worker. Please try again.',
            'PERMISSION_DENIED': 'Notification permission was denied. Please enable notifications in your browser settings.',
            'PERMISSION_REQUEST_FAILED': 'Failed to request notification permission.',
            'VAPID_KEY_FETCH_FAILED': 'Failed to get notification keys from server.',
            'PUSH_SUBSCRIPTION_FAILED': 'Failed to create push subscription.',
            'SERVER_SAVE_FAILED': 'Failed to save subscription to server. Please try again.'
        };

        return errorMessages[error.message] || `An error occurred: ${error.message}`;
    }

    /**
     * Log current step
     */
    async logStep(stepName) {
        this.steps.push(stepName);
        this.currentStep = this.steps.length - 1;
        console.log(`[OneClick] Step ${this.currentStep + 1}: ${stepName}`);
    }

    /**
     * Log to server for analytics
     */
    async logToServer(type, details) {
        try {
            await fetch('/api/push/enable-log', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    type: type,
                    timestamp: new Date().toISOString(),
                    userAgent: navigator.userAgent,
                    isIOS: this.isIOS,
                    isStandalone: this.isStandalone,
                    details: details
                })
            });
        } catch (error) {
            console.error('[OneClick] Failed to log to server:', error);
        }
    }

    /**
     * Convert VAPID key from base64url to Uint8Array
     */
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

    /**
     * Check if notifications are already enabled
     */
    async isEnabled() {
        try {
            if (Notification.permission !== 'granted') {
                return false;
            }

            const registration = await navigator.serviceWorker.getRegistration();
            if (!registration) {
                return false;
            }

            const subscription = await registration.pushManager.getSubscription();
            return !!subscription;

        } catch (error) {
            return false;
        }
    }

    /**
     * Disable notifications
     */
    async disableNotifications() {
        try {
            const registration = await navigator.serviceWorker.getRegistration();
            if (!registration) {
                return { success: true, message: 'No subscription to remove' };
            }

            const subscription = await registration.pushManager.getSubscription();
            if (!subscription) {
                return { success: true, message: 'No subscription to remove' };
            }

            const endpoint = subscription.endpoint;

            // Unsubscribe from push
            await subscription.unsubscribe();

            // Remove from server
            await fetch('/api/push/unsubscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ endpoint })
            });

            return { success: true, message: 'Notifications disabled successfully' };

        } catch (error) {
            return { success: false, error: error.message };
        }
    }
}

// Make available globally
window.OneClickPushManager = OneClickPushManager;

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = OneClickPushManager;
}