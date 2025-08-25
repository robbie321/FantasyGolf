self.addEventListener('install', event => {
    console.log('Service Worker: Install event fired.');
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    console.log('Service Worker: Activate event fired.');
});

self.addEventListener('push', event => {
    console.log('Service Worker: Push event received!');

    if (!event.data) {
        console.error('Service Worker: Push event had no data.');
        return;
    }

    try {
        const data = event.data.json();
        console.log('Service Worker: Push data parsed successfully:', data);

        const title = data.title || 'Fantasy Fairways';
        const options = {
            body: data.body,
            icon: data.icon || '/static/images/icons/icon-192x192.png',
            badge: '/static/images/icons/icon-192x192.png' // Badge for Android
        };

        event.waitUntil(self.registration.showNotification(title, options));
        console.log('Service Worker: Notification should now be displayed.');

    } catch (e) {
        console.error('Service Worker: Error parsing push data', e);
    }
});

self.addEventListener('notificationclick', event => {
    console.log('Service Worker: Notification was clicked.');
    event.notification.close();
    // This focuses the existing window or opens a new one
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
            if (clientList.length > 0) {
                let client = clientList[0];
                for (let i = 0; i < clientList.length; i++) {
                    if (clientList[i].focused) {
                        client = clientList[i];
                    }
                }
                return client.focus();
            }
            return clients.openWindow('/');
        })
    );
});