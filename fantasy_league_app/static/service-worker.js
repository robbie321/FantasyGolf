const CACHE_NAME = 'fantasy-golf-cache-v1';
const urlsToCache = [
  '/',
  '/static/css/base.css',
  // Add paths to all your other essential CSS, JS, and image files here
  '/offline.html' // The page to show when offline
];

// Install the service worker and cache the assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
  );
});

// Serve cached content when offline
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Cache hit - return response
        if (response) {
          return response;
        }
        // Not in cache - try to fetch from network
        return fetch(event.request).catch(() => {
          // Network failed - return offline page
          return caches.match('/offline.html');
        });
      })
  );
});


// Listen for incoming push notifications
self.addEventListener('push', event => {
    const data = event.data.json();
    console.log('Push notification received:', data);

    const title = data.title || 'Fantasy Fairways';
    const options = {
        body: data.body,
        icon: data.icon || '/static/images/icons/icon-192x192.png',
        badge: '/static/images/icons/icon-96x96.png'
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

// Handle notification click
self.addEventListener('notificationclick', event => {
    event.notification.close();
    event.waitUntil(
        clients.openWindow('/')
    );
});