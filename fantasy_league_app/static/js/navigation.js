/**
 * navigation.js - Professional SPA Navigation
 * Handles showing and hiding page sections and updating active states.
 */

export function setupNavigation() {
    // Select ALL navigation links that could trigger SPA-style navigation
    const navLinks = document.querySelectorAll('.sidebar-nav a, .mobile-nav a, .more-options-menu a');
    const pageSections = document.querySelectorAll('.page-section');

    const handleLinkClick = (targetId, clickedLink) => {
        if (!targetId || !targetId.startsWith('#')) {
            return; // Ignore links that don't start with #
        }

        // Hide all page sections
        pageSections.forEach(section => {
            section.classList.add('hidden');
        });

        // Show the target section
        const targetSection = document.querySelector(targetId);
        if (targetSection) {
            targetSection.classList.remove('hidden');
        }

        // Update active classes on all nav links
        navLinks.forEach(link => {
            const parent = link.parentElement;
            const linkHref = link.getAttribute('href') || '';

            // Handle sidebar (<li>) and mobile nav (<a>) active states
            const elementToActivate = parent.tagName === 'LI' ? parent : link;

            if (linkHref.endsWith(targetId)) {
                elementToActivate.classList.add('active');
            } else {
                elementToActivate.classList.remove('active');
            }
        });

        // Scroll to top when switching sections
        window.scrollTo(0, 0);
    };

    // Attach a single, unified event listener to all navigation links
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');

            // CRITICAL CHANGE: Only prevent default behavior if on a dashboard page
            if (href && href.includes('#') && window.location.pathname.includes('dashboard')) {
                e.preventDefault();

                const targetId = new URL(link.href).hash;
                handleLinkClick(targetId, link);

                history.pushState(null, '', targetId);
            }
            // If not on a dashboard page, the link will navigate as normal
        });
    });

    // On initial page load, only activate sections if on a dashboard page
    if (window.location.pathname.includes('dashboard')) {
        const currentHash = window.location.hash;
        if (currentHash && document.querySelector(currentHash)) {
            handleLinkClick(currentHash, document.querySelector(`a[href$="${currentHash}"]`));
        } else if (pageSections.length > 0) {
            // Default to showing the dashboard section
            handleLinkClick('#dashboard-section', document.querySelector('a[href$="#dashboard-section"]'));
        }
    }

    // Handle mobile "More Options" menu
    const moreButton = document.getElementById('more-btn');
    const moreMenu = document.querySelector('.more-options-menu');
    const moreMenuOverlay = document.querySelector('.more-options-overlay');
    const closeMenuButton = document.getElementById('close-menu-btn');

    const openMoreMenu = () => {
        if (moreMenu && moreMenuOverlay) {
            moreMenu.classList.add('open');
            moreMenuOverlay.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        }
    };

    const closeMoreMenu = () => {
        if (moreMenu && moreMenuOverlay) {
            moreMenu.classList.remove('open');
            moreMenuOverlay.classList.add('hidden');
            document.body.style.overflow = '';
        }
    };

    if (moreButton) moreButton.addEventListener('click', openMoreMenu);
    if (closeMenuButton) closeMenuButton.addEventListener('click', closeMoreMenu);
    if (moreMenuOverlay) moreMenuOverlay.addEventListener('click', closeMoreMenu);

    // Close menu when navigation link is clicked
    const moreMenuItems = document.querySelectorAll('.more-options-menu .menu-list a');
    moreMenuItems.forEach(link => {
        if (!link.classList.contains('logout-link')) {
            link.addEventListener('click', closeMoreMenu);
        }
    });
}