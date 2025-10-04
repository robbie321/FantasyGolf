/**
 * main.js - Professional Dashboard Entry Point
 * This file imports functionality from other modules and initializes
 * all the event listeners when the page loads.
 */
import { setupNavigation } from './navigation.js';
import { setupModalHandlers, setupSettingsHandlers } from './ui.js';
import { setupViews } from './views.js';
import { setupLeaderboards } from './leaderboard.js';

// ============================================
// SERVICE WORKER MESSAGE HANDLER
// Handle messages from service worker (Fix 6)
// ============================================
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', event => {
        console.log('[Main] Message from Service Worker:', event.data);

        if (event.data.type === 'NAVIGATE') {
            console.log('[Main] Navigating to:', event.data.url);
            window.location.href = event.data.url;
        } else if (event.data.type === 'NAVIGATE_HASH') {
            console.log('[Main] Navigating to hash:', event.data.hash);
            window.location.hash = event.data.hash;
            // Trigger hash change event for SPA navigation
            window.dispatchEvent(new HashChangeEvent('hashchange'));
        }
    });

    console.log('[Main] Service Worker message listener registered');
}

document.addEventListener('DOMContentLoaded', function() {
    console.log("Initializing professional dashboard application...");

    // Set up the main single-page application navigation
    setupNavigation();

    // Set up listeners for UI components like the "Join League" modal
    setupModalHandlers();

    // Set up settings form handlers
    setupSettingsHandlers();

    // Set up listeners for dynamically created content
    setupViews();

    // Load leaderboards and shared dashboard sections
    setupLeaderboards();

    // Fix mobile navigation display on desktop
    fixMobileNavigation();

    // Initialize professional animations
    initializeAnimations();

    console.log("Professional dashboard application initialized successfully.");
});

/**
 * Fix mobile navigation showing on desktop
 */
function fixMobileNavigation() {
    const mobileNav = document.querySelector('.mobile-nav');
    const sidebar = document.querySelector('.sidebar');

    function handleResize() {
        const isDesktop = window.innerWidth >= 1024;

        if (mobileNav) {
            mobileNav.style.display = isDesktop ? 'none' : 'flex';
        }

        if (sidebar) {
            sidebar.style.display = isDesktop ? 'flex' : 'none';
        }

        // Adjust dashboard content margin for mobile nav
        const dashboardContent = document.querySelector('.dashboard-content');
        if (dashboardContent) {
            dashboardContent.style.marginBottom = isDesktop ? '0' : '80px';
        }
    }

    // Initial check
    handleResize();

    // Listen for window resize
    window.addEventListener('resize', handleResize);
}

/**
 * Initialize professional animations and interactions
 */
function initializeAnimations() {
    // Animate elements on page load
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, { threshold: 0.1 });

    // Observe dashboard cards and sections
    document.querySelectorAll('.dashboard-league-card, .stat-card, .settings-card, .wallet-card').forEach((el, index) => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'opacity 0.6s ease-out, transform 0.6s ease-out';
        el.style.transitionDelay = `${index * 0.1}s`;
        observer.observe(el);
    });

    // Enhanced hover effects for interactive elements
    document.querySelectorAll('.dashboard-league-card, .btn').forEach(element => {
        element.addEventListener('mouseenter', function() {
            if (!this.classList.contains('no-hover')) {
                this.style.transform = 'translateY(-2px)';
            }
        });

        element.addEventListener('mouseleave', function() {
            if (!this.classList.contains('no-hover')) {
                this.style.transform = 'translateY(0)';
            }
        });
    });
}

/**
 * Utility function to show success notifications
 */
export function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <i class="fa-solid fa-${type === 'success' ? 'check-circle' : 'exclamation-triangle'}"></i>
            <span>${message}</span>
        </div>
        <button class="notification-close">
            <i class="fa-solid fa-times"></i>
        </button>
    `;

    // Add styles
    notification.style.cssText = `
        position: fixed;
        top: 2rem;
        right: 2rem;
        background: ${type === 'success' ? 'var(--success-gradient)' : 'var(--warning-bg)'};
        color: ${type === 'success' ? 'white' : 'var(--warning-text)'};
        padding: 1rem 1.5rem;
        border-radius: var(--border-radius);
        box-shadow: var(--shadow-lg);
        z-index: 3000;
        display: flex;
        align-items: center;
        gap: 1rem;
        animation: slideInRight 0.3s ease-out;
        max-width: 400px;
    `;

    document.body.appendChild(notification);

    // Auto remove after 5 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease-out';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);

    // Manual close
    const closeBtn = notification.querySelector('.notification-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            notification.style.animation = 'slideOutRight 0.3s ease-out';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        });
    }
}

// Add notification animations to CSS
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }

    .notification-content {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        flex: 1;
    }

    .notification-close {
        background: none;
        border: none;
        color: inherit;
        cursor: pointer;
        padding: 0.25rem;
        border-radius: 50%;
        transition: background-color 0.2s;
    }

    .notification-close:hover {
        background-color: rgba(255, 255, 255, 0.2);
    }
`;
document.head.appendChild(style);