// Enhanced Service Worker for Fantasy Fairways
// Handles push notifications, caching, and offline functionality

const CACHE_NAME = 'fantasy-fairways-v1.2.0';
const STATIC_CACHE = 'fantasy-fairways-static-v1.2.0';
const DYNAMIC_CACHE = 'fantasy-fairways-dynamic-v1.2.0';

// Define what to cache
const STATIC_ASSETS = [
    '/',
    '/static/css/style.css',
    '/static/css/LeaguesView/league_view.css',
    '/static/css/SharedSections/tour_leaderboard.css',
    '/static/css/auth/professional_login.css',
    '/static/css/form_style.css',
    '/static/js/main.js',
    '/static/js/navigation.js',
    '/static/js/ui.js',
    '/static/js/views.js',
    '/static/js/leaderboard.js',
    '/static/js/api.js',
    '/static/css/fa/css/fontawesome.css',
    '/static/css/fa/css/brands.css',
    '/static/css/fa/css/solid.css',
    '/static/manifest.json',
    '/offline'
];

// API endpoints that should be cached
const API_CACHE_PATTERNS = [
    /\/api\/live-leaderboard\/\w+/,
    /\/api\/tour-schedule\/\w+/,
    /\/league\/\d+/
];

// Install event - cache static assets
self.addEventListener('install', event => {
    console.log('[SW] Installing service worker...');

    event.waitUntil(
        Promise.all([
            // Cache static assets
            caches.open(STATIC_CACHE).then(cache => {
                console.log('[SW] Caching static assets');
                return cache.addAll(STATIC_ASSETS.map(url => {
                    return new Request(url, { cache: 'reload' });
                }));
            }),
            // Force activation
            self.skipWaiting()
        ])
    );
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
                        .filter(name => name !== STATIC_CACHE && name !== DYNAMIC_CACHE)
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

// Fetch event - serve from cache or network
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);

    // Handle different request types
    if (request.method === 'GET') {
        if (isStaticAsset(request.url)) {
            event.respondWith(handleStaticAsset(request));
        } else if (isAPIRequest(request.url)) {
            event.respondWith(handleAPIRequest(request));
        } else if (isNavigationRequest(request)) {
            event.respondWith(handleNavigationRequest(request));
        } else {
            event.respondWith(handleOtherRequests(request));
        }
    }
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
        Promise.all([
            // Show notification
            self.registration.showNotification(notificationData.title, {
                body: notificationData.body,
                icon: notificationData.icon,
                badge: notificationData.badge,
                tag: notificationData.tag,
                requireInteraction: notificationData.requireInteraction,
                data: notificationData.data,
                actions: notificationData.actions || [],
                image: notificationData.image,
                vibrate: notificationData.vibrate || [200, 100, 200],
                sound: notificationData.sound,
                timestamp: Date.now(),
                renotify: true
            }),
            // Log analytics (optional)
            logNotificationReceived(notificationData)
        ])
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

    // Optional: Log notification dismissal analytics
    const data = event.notification.data || {};
    logNotificationDismissed(data);
});

// Background sync for offline actions
self.addEventListener('sync', event => {
    console.log('[SW] Background sync triggered:', event.tag);

    if (event.tag === 'league-join') {
        event.waitUntil(syncLeagueJoin());
    } else if (event.tag === 'score-update') {
        event.waitUntil(syncScoreUpdates());
    }
});

// Helper Functions

function isStaticAsset(url) {
    return STATIC_ASSETS.some(asset => url.includes(asset)) ||
           url.includes('/static/') ||
           url.includes('.css') ||
           url.includes('.js') ||
           url.includes('.png') ||
           url.includes('.jpg') ||
           url.includes('.ico');
}

function isAPIRequest(url) {
    return API_CACHE_PATTERNS.some(pattern => pattern.test(url)) ||
           url.includes('/api/');
}

function isNavigationRequest(request) {
    return request.mode === 'navigate' ||
           (request.method === 'GET' && request.headers.get('accept').includes('text/html'));
}

async function handleStaticAsset(request) {
    try {
        // Try cache first
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }

        // Fetch from network and cache
        const networkResponse = await fetch(request);
        if (networkResponse.ok) {
            const cache = await caches.open(STATIC_CACHE);
            cache.put(request, networkResponse.clone());
        }
        return networkResponse;
    } catch (error) {
        console.error('[SW] Static asset fetch failed:', error);
        return caches.match(request);
    }
}

async function handleAPIRequest(request) {
    try {
        // Network first for API requests
        const networkResponse = await fetch(request);

        if (networkResponse.ok) {
            // Cache successful API responses
            const cache = await caches.open(DYNAMIC_CACHE);
            cache.put(request, networkResponse.clone());
        }

        return networkResponse;
    } catch (error) {
        console.log('[SW] API request failed, trying cache:', error);

        // Fallback to cache
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }

        // Return offline indicator for API failures
        return new Response(JSON.stringify({
            error: 'Offline',
            message: 'This content is not available offline'
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

async function handleNavigationRequest(request) {
    try {
        // Try network first
        const networkResponse = await fetch(request);
        return networkResponse;
    } catch (error) {
        console.log('[SW] Navigation request failed, trying cache:', error);

        // Try to find cached page
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }

        // Fallback to offline page
        return caches.match('/offline') ||
               new Response('Offline - Please check your connection', {
                   status: 503,
                   headers: { 'Content-Type': 'text/html' }
               });
    }
}

async function handleOtherRequests(request) {
    try {
        // Try cache first for other requests
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }

        // Fetch from network
        const networkResponse = await fetch(request);

        // Cache if successful
        if (networkResponse.ok) {
            const cache = await caches.open(DYNAMIC_CACHE);
            cache.put(request, networkResponse.clone());
        }

        return networkResponse;
    } catch (error) {
        console.error('[SW] Request failed:', error);
        return new Response('Service Unavailable', { status: 503 });
    }
}

function enhanceNotification(data) {
    const enhancements = {
        'league_update': {
            title: '🏆 League Update',
            icon: '/static/images/league-icon.png',
            requireInteraction: true,
            actions: [
                {
                    action: 'view-league',
                    title: 'View League',
                    icon: '/static/images/action-view.png'
                },
                {
                    action: 'dismiss',
                    title: 'Dismiss',
                    icon: '/static/images/action-dismiss.png'
                }
            ]
        },
        'score_update': {
            title: '⛳ Score Update',
            icon: '/static/images/score-icon.png',
            vibrate: [100, 50, 100],
            actions: [
                {
                    action: 'view-leaderboard',
                    title: 'View Leaderboard',
                    icon: '/static/images/action-leaderboard.png'
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
                    title: 'Watch Live',
                    icon: '/static/images/action-live.png'
                },
                {
                    action: 'view-team',
                    title: 'My Team',
                    icon: '/static/images/action-team.png'
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
                    title: 'View Winnings',
                    icon: '/static/images/action-money.png'
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
        'view-league': () => navigateToUrl(data.leagueUrl || '/dashboard#leagues'),
        'view-leaderboard': () => navigateToUrl(data.leaderboardUrl || '/dashboard#leaderboards'),
        'view-live': () => navigateToUrl(data.liveUrl || '/dashboard#leaderboards'),
        'view-team': () => navigateToUrl(data.teamUrl || '/dashboard'),
        'view-winnings': () => navigateToUrl(data.winningsUrl || '/dashboard#wallet'),
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

// Background sync functions
async function syncLeagueJoin() {
    try {
        // Get pending league joins from IndexedDB
        const pendingJoins = await getPendingLeagueJoins();

        for (const join of pendingJoins) {
            try {
                const response = await fetch('/api/join-league', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': join.csrfToken
                    },
                    body: JSON.stringify({ league_code: join.leagueCode })
                });

                if (response.ok) {
                    await removePendingLeagueJoin(join.id);

                    // Show success notification
                    await self.registration.showNotification('League Joined!', {
                        body: `Successfully joined league: ${join.leagueCode}`,
                        icon: '/static/images/success-icon.png',
                        tag: 'league-join-success'
                    });
                }
            } catch (error) {
                console.error('[SW] Failed to sync league join:', error);
            }
        }
    } catch (error) {
        console.error('[SW] Sync league join failed:', error);
    }
}

async function syncScoreUpdates() {
    // Implementation for syncing score updates when back online
    console.log('[SW] Syncing score updates...');
}

// Analytics functions
async function logNotificationReceived(data) {
    try {
        await fetch('/api/analytics/notification-received', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: data.type,
                timestamp: Date.now(),
                tag: data.tag
            })
        });
    } catch (error) {
        console.log('[SW] Failed to log notification received:', error);
    }
}

async function logNotificationClicked(data) {
    try {
        await fetch('/api/analytics/notification-clicked', {
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
        await fetch('/api/analytics/notification-dismissed', {
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
        await fetch('/api/analytics/notification-action', {
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

// IndexedDB helper functions for offline storage
async function getPendingLeagueJoins() {
    // Implementation would use IndexedDB to get pending joins
    return [];
}

async function removePendingLeagueJoin(id) {
    // Implementation would remove from IndexedDB
}

console.log('[SW] Service Worker registered successfully');