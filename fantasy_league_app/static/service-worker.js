// Enhanced Service Worker for Fantasy Fairways
// Handles push notifications, caching, and offline functionality

const CACHE_NAME = 'fantasy-fairways-v1.0.0';
const STATIC_CACHE = 'fantasy-fairways-static-v1.0.0';

// Define what to cache
const STATIC_ASSETS = [
    '/',
    '/static/css/style.css',
    '/static/js/main.js',
    '/static/manifest.json',
    '/offline'
];

// Install event - cache static assets
self.addEventListener('install', event => {
    console.log('[SW] Installing service worker...');

    event.waitUntil(
        caches.open(STATIC_CACHE).then(cache => {
            console.log('[SW] Caching static assets');
            return cache.addAll(STATIC_ASSETS.map(url => {
                return new Request(url, { cache: 'reload' });
            }));
        }).catch(err => {
            console.log('[SW] Cache install failed:', err);
        })
    );

    // Force activation
    self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
    console.log('[SW] Activating service worker...');

    event.waitUntil(
        Promise.all([
            // Clean up old caches
            caches.keys().then(cacheNames => {
                return Promise.all(
                    cacheNames
                        .filter(name => name !== STATIC_CACHE && name.startsWith('fantasy-fairways-'))
                        .map(name => {
                            console.log('[SW] Deleting old cache:', name);
                            return caches.delete(name);
                        })
                );
            }),
            // Take control of all clients
            self.clients.claim()
        ])
    );
});

// Push notification event handler
self.addEventListener('push', event => {
    console.log('[SW] Push notification received:', event);

    let notificationData = {
        title: 'Fantasy Fairways',
        body: 'You have a new update!',
        icon: '/static/images/icon-192x192.png',
        badge: '/static/images/badge-72x72.png',
        tag: 'general',
        requireInteraction: false,
        data: {}
    };

    // Parse push data if available
    if (event.data) {
        try {
            const pushData = event.data.json();
            notificationData = { ...notificationData, ...pushData };
        } catch (e) {
            console.error('[SW] Error parsing push data:', e);
            notificationData.body = event.data.text() || notificationData.body;
        }
    }

    // Enhance notification based on type
    if (notificationData.type) {
        notificationData = enhanceNotification(notificationData);
    }

    event.waitUntil(
        self.registration.showNotification(notificationData.title, {
            body: notificationData.body,
            icon: notificationData.icon,
            badge: notificationData.badge,
            tag: notificationData.tag,
            requireInteraction: notificationData.requireInteraction,
            data: notificationData.data,
            actions: notificationData.actions || [],
            vibrate: notificationData.vibrate || [200, 100, 200],
            timestamp: Date.now(),
            renotify: true
        })
    );
});

// Notification click event handler
self.addEventListener('notificationclick', event => {
    console.log('[SW] Notification clicked:', event.notification);

    const notification = event.notification;
    const data = notification.data || {};

    // Close the notification
    notification.close();

    // Handle different click actions
    if (event.action) {
        handleNotificationAction(event.action, data);
    } else {
        handleNotificationClick(data);
    }
});

// Notification close event handler
self.addEventListener('notificationclose', event => {
    console.log('[SW] Notification closed:', event.notification);

    // Log notification dismissal analytics
    const data = event.notification.data || {};
    logNotificationDismissed(data);
});

// Helper function to enhance notifications
function enhanceNotification(data) {
    const enhancements = {
        'league_update': {
            title: '🏆 League Update',
            icon: '/static/images/icon-192x192.png',
            requireInteraction: true,
            actions: [
                {
                    action: 'view-league',
                    title: 'View League'
                },
                {
                    action: 'dismiss',
                    title: 'Dismiss'
                }
            ]
        },
        'score_update': {
            title: '⛳ Score Update',
            icon: '/static/images/icon-192x192.png',
            vibrate: [100, 50, 100],
            actions: [
                {
                    action: 'view-leaderboard',
                    title: 'View Leaderboard'
                }
            ]
        },
        'tournament_start': {
            title: '🚀 Tournament Started!',
            requireInteraction: true,
            vibrate: [200, 100, 200, 100, 200],
            actions: [
                {
                    action: 'view-live',
                    title: 'Watch Live'
                },
                {
                    action: 'view-team',
                    title: 'My Team'
                }
            ]
        },
        'prize_won': {
            title: '🎉 Congratulations!',
            requireInteraction: true,
            vibrate: [300, 100, 300, 100, 300],
            actions: [
                {
                    action: 'view-winnings',
                    title: 'View Winnings'
                }
            ]
        }
    };

    const enhancement = enhancements[data.type];
    if (enhancement) {
        return { ...data, ...enhancement };
    }

    return data;
}

async function handleNotificationClick(data) {
    const urlToOpen = data.url || '/dashboard';

    try {
        // Check if any client is already open
        const clients = await self.clients.matchAll({
            type: 'window',
            includeUncontrolled: true
        });

        // If a client is open, focus it and navigate
        if (clients.length > 0) {
            const client = clients[0];
            client.focus();
            client.postMessage({
                type: 'NAVIGATE',
                url: urlToOpen,
                data: data
            });
        } else {
            // Open new window
            await self.clients.openWindow(urlToOpen);
        }

        // Log analytics
        logNotificationClicked(data);
    } catch (error) {
        console.error('[SW] Error handling notification click:', error);
    }
}

async function handleNotificationAction(action, data) {
    const actions = {
        'view-league': () => navigateToUrl(data.url || '/dashboard'),
        'view-leaderboard': () => navigateToUrl('/dashboard#leaderboards'),
        'view-live': () => navigateToUrl('/dashboard#leaderboards'),
        'view-team': () => navigateToUrl('/dashboard'),
        'view-winnings': () => navigateToUrl('/dashboard'),
        'dismiss': () => Promise.resolve()
    };

    const actionHandler = actions[action];
    if (actionHandler) {
        await actionHandler();
        logNotificationAction(action, data);
    }
}

async function navigateToUrl(url) {
    try {
        const clients = await self.clients.matchAll({
            type: 'window',
            includeUncontrolled: true
        });

        if (clients.length > 0) {
            const client = clients[0];
            client.focus();
            client.postMessage({ type: 'NAVIGATE', url: url });
        } else {
            await self.clients.openWindow(url);
        }
    } catch (error) {
        console.error('[SW] Error navigating to URL:', error);
    }
}

// Analytics functions
async function logNotificationClicked(data) {
    try {
        await fetch('/api/push/analytics/notification-clicked', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: data.type,
                timestamp: Date.now(),
                tag: data.tag
            })
        });
    } catch (error) {
        console.log('[SW] Failed to log notification clicked:', error);
    }
}

async function logNotificationDismissed(data) {
    try {
        await fetch('/api/push/analytics/notification-dismissed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: data.type,
                timestamp: Date.now(),
                tag: data.tag
            })
        });
    } catch (error) {
        console.log('[SW] Failed to log notification dismissed:', error);
    }
}

async function logNotificationAction(action, data) {
    try {
        await fetch('/api/push/analytics/notification-action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: action,
                type: data.type,
                timestamp: Date.now(),
                tag: data.tag
            })
        });
    } catch (error) {
        console.log('[SW] Failed to log notification action:', error);
    }
}

// Listen for messages from main thread
self.addEventListener('message', event => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

console.log('[SW] Service Worker registered successfully');