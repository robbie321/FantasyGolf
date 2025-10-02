// static/js/service-worker.js
// Enhanced Service Worker for Fantasy Fairways
// Handles push notifications, caching, and offline functionality

const CACHE_NAME = 'fantasy-fairways-v1.0.1';
const STATIC_CACHE = 'fantasy-fairways-static-v1.0.1';

// Define what to cache - only files that exist
const STATIC_ASSETS = [
    '/',
    '/static/css/style.css',
    '/static/js/main.js',
    '/static/manifest.json',
    '/offline'
];

// Install event - cache static assets with better error handling
self.addEventListener('install', event => {
    console.log('[SW] Installing service worker...');

    event.waitUntil(
        caches.open(STATIC_CACHE).then(cache => {
            console.log('[SW] Caching static assets');
            // Cache each file individually to avoid one failure breaking everything
            return Promise.allSettled(
                STATIC_ASSETS.map(url => {
                    return cache.add(new Request(url, { cache: 'reload' }))
                        .catch(err => {
                            console.warn(`[SW] Failed to cache ${url}:`, err);
                        });
                })
            );
        }).then(() => {
            console.log('[SW] Cache install completed (some files may have failed)');
        }).catch(err => {
            console.error('[SW] Cache install failed:', err);
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

// Fetch event - network first, fall back to cache
self.addEventListener('fetch', event => {
    event.respondWith(
        fetch(event.request)
            .then(response => {
                // Clone and cache successful responses
                if (response && response.status === 200 && response.type === 'basic') {
                    const responseToCache = response.clone();
                    caches.open(STATIC_CACHE)
                        .then(cache => cache.put(event.request, responseToCache))
                        .catch(err => console.warn('[SW] Cache put failed:', err));
                }
                return response;
            })
            .catch(() => {
                // Network failed, try cache
                return caches.match(event.request);
            })
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
        data: {
            url: '/dashboard',
            timestamp: Date.now()
        }
    };

    // Parse push data if available
    if (event.data) {
        try {
            const pushData = event.data.json();
            console.log('[SW] Push data:', pushData);

            notificationData = {
                title: pushData.title || notificationData.title,
                body: pushData.body || notificationData.body,
                icon: pushData.icon || notificationData.icon,
                badge: pushData.badge || notificationData.badge,
                tag: pushData.tag || notificationData.tag,
                requireInteraction: pushData.requireInteraction || false,
                data: {
                    url: pushData.data?.url || pushData.url || '/dashboard',
                    type: pushData.type || 'general',
                    timestamp: Date.now(),
                    ...pushData.data
                }
            };

            // Add actions if provided
            if (pushData.actions && Array.isArray(pushData.actions)) {
                notificationData.actions = pushData.actions;
            }

            // Add vibration if provided
            if (pushData.vibrate && Array.isArray(pushData.vibrate)) {
                notificationData.vibrate = pushData.vibrate;
            }

            // Enhance based on notification type
            notificationData = enhanceNotification(notificationData);

        } catch (e) {
            console.error('[SW] Error parsing push data:', e);
            notificationData.body = event.data.text() || notificationData.body;
        }
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
        }).then(() => {
            console.log('[SW] Notification shown successfully');
        }).catch(error => {
            console.error('[SW] Error showing notification:', error);
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
    event.waitUntil(
        (async () => {
            if (event.action) {
                await handleNotificationAction(event.action, data);
            } else {
                await handleNotificationClick(data);
            }
        })()
    );
});

// Notification close event handler
self.addEventListener('notificationclose', event => {
    console.log('[SW] Notification closed:', event.notification);

    // Log notification dismissal analytics
    const data = event.notification.data || {};
    event.waitUntil(logNotificationDismissed(data));
});

// Helper function to enhance notifications
function enhanceNotification(data) {
    const enhancements = {
        'league_update': {
            icon: '/static/images/icon-192x192.png',
            requireInteraction: true,
            actions: [
                { action: 'view-league', title: 'View League' },
                { action: 'dismiss', title: 'Dismiss' }
            ]
        },
        'score_update': {
            icon: '/static/images/icon-192x192.png',
            vibrate: [100, 50, 100],
            actions: [
                { action: 'view-leaderboard', title: 'View Leaderboard' }
            ]
        },
        'tournament_start': {
            requireInteraction: true,
            vibrate: [200, 100, 200, 100, 200],
            actions: [
                { action: 'view-live', title: 'Watch Live' },
                { action: 'view-team', title: 'My Team' }
            ]
        },
        'prize_won': {
            requireInteraction: true,
            vibrate: [300, 100, 300, 100, 300],
            actions: [
                { action: 'view-winnings', title: 'View Winnings' }
            ]
        },
        'test': {
            icon: '/static/images/icon-192x192.png',
            requireInteraction: false
        }
    };

    const enhancement = enhancements[data.type || data.data?.type];
    if (enhancement) {
        return {
            ...data,
            ...enhancement,
            // Keep existing actions if they exist
            actions: enhancement.actions || data.actions
        };
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
            await client.focus();
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
        await logNotificationClicked(data);
    } catch (error) {
        console.error('[SW] Error handling notification click:', error);
    }
}

async function handleNotificationAction(action, data) {
    const actions = {
        'view-league': () => navigateToUrl(data.url || '/user_dashboard'),
        'view-leaderboard': () => navigateToUrl('/user_dashboard#leaderboards'),
        'view-live': () => navigateToUrl('/user_dashboard#leaderboards'),
        'view-team': () => navigateToUrl('/user_dashboard'),
        'view-winnings': () => navigateToUrl('/user_dashboard'),
        'dismiss': () => Promise.resolve()
    };

    const actionHandler = actions[action];
    if (actionHandler) {
        await actionHandler();
        await logNotificationAction(action, data);
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
            await client.focus();
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