// static/js/service-worker.js
// Enhanced service worker with iOS compatibility

const CACHE_NAME = 'fantasy-golf-v1';
const urlsToCache = [
    '/',
    '/static/css/style.css',
    '/static/images/icon-192x192.png',
    '/static/images/icon-512x512.png'
];

// Install event - cache resources
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Installing...');

    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[Service Worker] Caching app shell');
                return cache.addAll(urlsToCache);
            })
            .catch((error) => {
                console.error('[Service Worker] Cache failed:', error);
            })
    );

    // Force the waiting service worker to become the active service worker
    self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activating...');

    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[Service Worker] Removing old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );

    // Claim all clients immediately
    return self.clients.claim();
});

// Fetch event - serve from cache when possible
self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request)
            .then((response) => {
                // Cache hit - return response
                if (response) {
                    return response;
                }

                // Clone the request
                const fetchRequest = event.request.clone();

                return fetch(fetchRequest).then((response) => {
                    // Check if valid response
                    if (!response || response.status !== 200 || response.type !== 'basic') {
                        return response;
                    }

                    // Clone the response
                    const responseToCache = response.clone();

                    caches.open(CACHE_NAME)
                        .then((cache) => {
                            cache.put(event.request, responseToCache);
                        });

                    return response;
                });
            })
    );
});

// Push event - handle incoming push notifications
self.addEventListener('push', (event) => {
    console.log('[Service Worker] Push received');

    let notificationData = {
        title: 'Fantasy Golf',
        body: 'You have a new notification',
        icon: '/static/images/icon-192x192.png',
        badge: '/static/images/badge-72x72.png',
        tag: 'default',
        requireInteraction: false,
        data: {
            url: '/',
            timestamp: Date.now()
        }
    };

    // Parse the push payload
    if (event.data) {
        try {
            const payload = event.data.json();
            console.log('[Service Worker] Push payload:', payload);

            notificationData = {
                title: payload.title || notificationData.title,
                body: payload.body || notificationData.body,
                icon: payload.icon || notificationData.icon,
                badge: payload.badge || notificationData.badge,
                tag: payload.tag || notificationData.tag,
                requireInteraction: payload.requireInteraction || false,
                data: {
                    url: payload.data?.url || payload.url || '/',
                    type: payload.type || 'general',
                    timestamp: Date.now(),
                    ...payload.data
                }
            };

            // Add actions if provided
            if (payload.actions && Array.isArray(payload.actions)) {
                notificationData.actions = payload.actions;
            }

            // Add vibration pattern if provided
            if (payload.vibrate && Array.isArray(payload.vibrate)) {
                notificationData.vibrate = payload.vibrate;
            }

            // iOS-specific: Add renotify and silent options
            if (isIOS()) {
                notificationData.renotify = true;
                notificationData.silent = false;
            }

        } catch (error) {
            console.error('[Service Worker] Error parsing push payload:', error);
            notificationData.body = event.data.text();
        }
    }

    // Show the notification
    event.waitUntil(
        self.registration.showNotification(notificationData.title, notificationData)
            .then(() => {
                console.log('[Service Worker] Notification shown successfully');

                // Log to analytics endpoint
                return fetch('/api/push/analytics/notification-received', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        type: notificationData.data.type,
                        tag: notificationData.tag,
                        timestamp: notificationData.data.timestamp
                    })
                }).catch(err => {
                    console.warn('[Service Worker] Analytics logging failed:', err);
                });
            })
            .catch((error) => {
                console.error('[Service Worker] Error showing notification:', error);
            })
    );
});

// Notification click event
self.addEventListener('notificationclick', (event) => {
    console.log('[Service Worker] Notification clicked:', event.notification.tag);

    event.notification.close();

    const urlToOpen = event.notification.data?.url || '/';

    // Log click analytics
    event.waitUntil(
        fetch('/api/push/analytics/notification-clicked', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                type: event.notification.data?.type,
                tag: event.notification.tag,
                action: event.action || 'default',
                timestamp: Date.now()
            })
        }).catch(err => {
            console.warn('[Service Worker] Click analytics failed:', err);
        }).then(() => {
            // Handle notification action
            if (event.action) {
                console.log('[Service Worker] Action clicked:', event.action);

                // Handle different actions
                switch(event.action) {
                    case 'view-league':
                    case 'view-leaderboard':
                    case 'view-live':
                    case 'view-team':
                    case 'view-winnings':
                        // Open the URL associated with the notification
                        return clients.openWindow(urlToOpen);
                    case 'dismiss':
                        // Just close the notification (already done above)
                        return Promise.resolve();
                    default:
                        return clients.openWindow(urlToOpen);
                }
            } else {
                // Default action - open the URL
                return clients.openWindow(urlToOpen);
            }
        }).then((windowClient) => {
            // Focus the window if it's already open
            if (windowClient) {
                return windowClient.focus();
            }
        })
    );
});

// Notification close event
self.addEventListener('notificationclose', (event) => {
    console.log('[Service Worker] Notification closed:', event.notification.tag);

    // Log dismissal analytics
    event.waitUntil(
        fetch('/api/push/analytics/notification-dismissed', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                type: event.notification.data?.type,
                tag: event.notification.tag,
                timestamp: Date.now()
            })
        }).catch(err => {
            console.warn('[Service Worker] Dismissal analytics failed:', err);
        })
    );
});

// Message event - handle messages from the client
self.addEventListener('message', (event) => {
    console.log('[Service Worker] Message received:', event.data);

    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }

    if (event.data && event.data.type === 'GET_VERSION') {
        event.ports[0].postMessage({
            version: CACHE_NAME
        });
    }
});

// Helper function to detect iOS
function isIOS() {
    return /iPad|iPhone|iPod/.test(self.navigator.userAgent);
}

// Sync event - for background sync (if supported)
self.addEventListener('sync', (event) => {
    console.log('[Service Worker] Background sync:', event.tag);

    if (event.tag === 'sync-notifications') {
        event.waitUntil(
            // Sync notification preferences or check for new notifications
            syncNotifications()
        );
    }
});

async function syncNotifications() {
    try {
        // Check if there are any pending notifications to sync
        const response = await fetch('/api/push/sync-check');

        if (response.ok) {
            const data = await response.json();

            if (data.hasPending) {
                console.log('[Service Worker] Pending notifications found');
                // The server will push them, so we just log here
            }
        }
    } catch (error) {
        console.error('[Service Worker] Sync failed:', error);
    }
}

console.log('[Service Worker] Script loaded');