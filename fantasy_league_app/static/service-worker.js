// static/service-worker.js
// Enhanced Service Worker for Fantasy Fairways
// Handles push notifications, caching, and offline functionality

const CACHE_NAME = 'fantasy-fairways-v1.0.2';
const STATIC_CACHE = 'fantasy-fairways-static-v1.0.2';

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

// ============================================
// ENHANCED PUSH NOTIFICATION EVENT HANDLER
// Fix 6: Android & iOS Compatibility
// ============================================
self.addEventListener('push', function(event) {
    console.log('[SW] Push notification received:', event);
    console.log('[SW] Push event data exists:', !!event.data);

    // Default notification configuration
    let notificationData = {
        title: 'Fantasy Fairways',
        body: 'You have a new notification',
        icon: '/static/images/icon-192x192.png',
        badge: '/static/images/badge-72x72.png',
        tag: 'default',
        requireInteraction: false,
        data: {
            url: '/dashboard',
            timestamp: Date.now()
        }
    };

    // Parse push event data
    if (event.data) {
        try {
            // Try to parse as JSON first
            const pushData = event.data.json();
            console.log('[SW] Parsed push data:', pushData);

            // Build notification from push data
            notificationData = {
                title: pushData.title || notificationData.title,
                body: pushData.body || notificationData.body,
                icon: pushData.icon || notificationData.icon,
                badge: pushData.badge || notificationData.badge,
                tag: pushData.tag || notificationData.tag,
                requireInteraction: pushData.requireInteraction || false,
                // Handle nested data object properly
                data: {
                    url: pushData.data?.url || pushData.url || '/dashboard',
                    type: pushData.data?.type || pushData.type || 'general',
                    timestamp: Date.now(),
                    // Preserve any additional data
                    ...(pushData.data || {})
                }
            };

            // Add actions if provided (Android & Chrome support)
            if (pushData.actions && Array.isArray(pushData.actions)) {
                notificationData.actions = pushData.actions.map(action => ({
                    action: action.action,
                    title: action.title,
                    icon: action.icon || undefined
                }));
            }

            // Add vibration pattern if provided (Android support)
            if (pushData.vibrate && Array.isArray(pushData.vibrate)) {
                notificationData.vibrate = pushData.vibrate;
            }

            // Apply type-based enhancements
            notificationData = enhanceNotification(notificationData);

        } catch (e) {
            console.error('[SW] Error parsing push data as JSON:', e);
            // Fallback to text if JSON parsing fails
            try {
                const textData = event.data.text();
                console.log('[SW] Push data as text:', textData);
                notificationData.body = textData || notificationData.body;
            } catch (textError) {
                console.error('[SW] Error parsing push data as text:', textError);
            }
        }
    } else {
        console.warn('[SW] No push data received, using defaults');
    }

    // Show the notification
    const promiseChain = self.registration.showNotification(
        notificationData.title,
        {
            body: notificationData.body,
            icon: notificationData.icon,
            badge: notificationData.badge,
            tag: notificationData.tag,
            requireInteraction: notificationData.requireInteraction,
            data: notificationData.data,
            actions: notificationData.actions || [],
            vibrate: notificationData.vibrate || [200, 100, 200],
            timestamp: Date.now(),
            renotify: true,
            // Android-specific options
            silent: false,
            // iOS compatibility
            dir: 'auto',
            lang: 'en'
        }
    ).then(() => {
        console.log('[SW] ✅ Notification shown successfully');
    }).catch(error => {
        console.error('[SW] ❌ Error showing notification:', error);
        // Fallback: try showing a simpler notification
        return self.registration.showNotification(
            notificationData.title,
            {
                body: notificationData.body,
                icon: notificationData.icon,
                data: notificationData.data
            }
        );
    });

    event.waitUntil(promiseChain);
});

// ============================================
// ENHANCED NOTIFICATION CLICK HANDLER
// Fix 6: Better client handling for Android & iOS
// ============================================
self.addEventListener('notificationclick', function(event) {
    console.log('[SW] Notification clicked:', event.notification.tag);
    console.log('[SW] Action clicked:', event.action || 'default');

    const notification = event.notification;
    const data = notification.data || {};

    // Close the notification immediately
    notification.close();

    // Determine URL to open
    let urlToOpen = '/';

    if (event.action) {
        // Handle specific action clicks
        const actionUrls = {
            'view-league': data.url || '/user_dashboard',
            'view-leaderboard': '/user_dashboard#leaderboards-section',
            'view-live': '/user_dashboard#leaderboards-section',
            'view-team': '/user_dashboard#dashboard-section',
            'view-winnings': '/user_dashboard',
            'dismiss': null
        };
        urlToOpen = actionUrls[event.action];

        // If dismiss action, just close notification
        if (event.action === 'dismiss') {
            console.log('[SW] Notification dismissed via action');
            event.waitUntil(logNotificationAction(event.action, data));
            return;
        }
    } else {
        // Default click - use URL from notification data
        urlToOpen = data.url || '/dashboard';
    }

    console.log('[SW] Opening URL:', urlToOpen);

    // Handle navigation
    event.waitUntil(
        clients.matchAll({
            type: 'window',
            includeUncontrolled: true
        })
        .then(function(clientList) {
            console.log('[SW] Found', clientList.length, 'open clients');

            // Try to find an existing client to focus
            for (let i = 0; i < clientList.length; i++) {
                const client = clientList[i];
                console.log('[SW] Checking client:', client.url);

                // If we find a matching client, focus it
                if (client.url.includes(urlToOpen.split('#')[0]) && 'focus' in client) {
                    console.log('[SW] Focusing existing client');
                    // Navigate to specific section if hash exists
                    if (urlToOpen.includes('#')) {
                        client.postMessage({
                            type: 'NAVIGATE_HASH',
                            hash: urlToOpen.split('#')[1]
                        });
                    }
                    return client.focus();
                }

                // Otherwise focus the first available client and navigate
                if ('focus' in client) {
                    console.log('[SW] Focusing first available client');
                    client.postMessage({
                        type: 'NAVIGATE',
                        url: urlToOpen
                    });
                    return client.focus();
                }
            }

            // No clients found, open new window
            console.log('[SW] No existing clients, opening new window');
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
        .then(() => {
            // Log analytics
            if (event.action) {
                return logNotificationAction(event.action, data);
            } else {
                return logNotificationClicked(data);
            }
        })
        .catch(error => {
            console.error('[SW] Error handling notification click:', error);
        })
    );
});

// Notification close event handler
self.addEventListener('notificationclose', event => {
    console.log('[SW] Notification closed:', event.notification.tag);

    // Log notification dismissal analytics
    const data = event.notification.data || {};
    event.waitUntil(logNotificationDismissed(data));
});

// Helper function to enhance notifications based on type
function enhanceNotification(data) {
    const type = data.data?.type || 'general';

    const enhancements = {
        'league_update': {
            icon: '/static/images/icon-192x192.png',
            requireInteraction: true,
            vibrate: [200, 100, 200],
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
        'rank_change': {
            vibrate: [100, 100, 100],
            actions: [
                { action: 'view-league', title: 'View League' }
            ]
        },
        'test': {
            icon: '/static/images/icon-192x192.png',
            requireInteraction: false,
            vibrate: [200]
        }
    };

    const enhancement = enhancements[type] || {};

    // Merge enhancement with existing data
    return {
        ...data,
        icon: enhancement.icon || data.icon,
        requireInteraction: enhancement.requireInteraction !== undefined
            ? enhancement.requireInteraction
            : data.requireInteraction,
        vibrate: enhancement.vibrate || data.vibrate,
        // Only add actions if not already present
        actions: data.actions || enhancement.actions || []
    };
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
        console.log('[SW] Logged notification clicked');
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
        console.log('[SW] Logged notification dismissed');
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
        console.log('[SW] Logged notification action:', action);
    } catch (error) {
        console.log('[SW] Failed to log notification action:', error);
    }
}

// Listen for messages from main thread
self.addEventListener('message', event => {
    console.log('[SW] Message received:', event.data);

    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

console.log('[SW] Service Worker v1.0.2 registered successfully');