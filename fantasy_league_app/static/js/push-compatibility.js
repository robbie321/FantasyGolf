// iOS Push Notification Compatibility Layer
class PushCompatibility {
  static async checkSupport() {
    const checks = {
      notifications: 'Notification' in window,
      serviceWorker: 'serviceWorker' in navigator,
      pushManager: 'PushManager' in window,
      isIOS: /iPad|iPhone|iPod/.test(navigator.userAgent),
      isStandalone: window.navigator.standalone === true,
      iOSVersion: this.getiOSVersion()
    };

    console.log('Push compatibility checks:', checks);
    return checks;
  }

  static getiOSVersion() {
    const match = navigator.userAgent.match(/OS (\d+)_/);
    return match ? parseInt(match[1]) : null;
  }

  static async ensureServiceWorkerReady() {
    if (!('serviceWorker' in navigator)) {
      throw new Error('Service Workers not supported');
    }

    let registration = await navigator.serviceWorker.getRegistration();

    if (!registration) {
      console.log('Registering service worker from root...');
      registration = await navigator.serviceWorker.register('/service-worker.js', {
        scope: '/',
        updateViaCache: 'none'
      });
    }

    // Wait for service worker to be ready
    await navigator.serviceWorker.ready;

    // Extra check for iOS - ensure it's actually active
    if (registration.active && registration.active.state === 'activated') {
      console.log('✅ Service worker is active and ready');
      return registration;
    }

    // Wait for activation
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Service worker activation timeout'));
      }, 10000);

      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing;
        newWorker.addEventListener('statechange', () => {
          if (newWorker.state === 'activated') {
            clearTimeout(timeout);
            resolve(registration);
          }
        });
      });

      // If already activated
      if (registration.active) {
        clearTimeout(timeout);
        resolve(registration);
      }
    });
  }

  static async requestPermission() {
    const checks = await this.checkSupport();

    // iOS requires PWA mode
    if (checks.isIOS && !checks.isStandalone) {
      throw new Error('iOS requires app to be added to home screen first');
    }

    // iOS 16.4+ required for push
    if (checks.isIOS && checks.iOSVersion && checks.iOSVersion < 16) {
      throw new Error(`iOS ${checks.iOSVersion} does not support web push (requires 16.4+)`);
    }

    const permission = await Notification.requestPermission();
    return permission;
  }

  static async subscribe(vapidPublicKey) {
    try {
      const registration = await this.ensureServiceWorkerReady();

      // Check for existing subscription
      let subscription = await registration.pushManager.getSubscription();

      if (subscription) {
        console.log('Existing subscription found, unsubscribing first...');
        await subscription.unsubscribe();
      }

      // Convert VAPID key
      const applicationServerKey = this.urlBase64ToUint8Array(vapidPublicKey);

      // Subscribe
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey
      });

      console.log('✅ Push subscription created');
      return subscription;

    } catch (error) {
      console.error('❌ Subscription failed:', error);
      throw error;
    }
  }

  static urlBase64ToUint8Array(base64String) {
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
}

export default PushCompatibility;