/**
 * navigation.js - SPA Navigation
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
}

// export function setupNavigation() {
//     // Select ALL navigation links that should trigger SPA-style navigation
//     const navLinks = document.querySelectorAll('.sidebar-nav a, .mobile-nav a, .more-options-menu a');
//     const pageSections = document.querySelectorAll('.page-section');

//     const handleLinkClick = (targetId, clickedLink) => {
//         if (!targetId || !targetId.startsWith('#')) {
//             return; // Ignore links that don't start with #
//         }

//         // Hide all page sections
//         pageSections.forEach(section => {
//             section.classList.add('hidden');
//         });

//         // Show the target section
//         const targetSection = document.querySelector(targetId);
//         if (targetSection) {
//             targetSection.classList.remove('hidden');
//         }

//         // Update active classes on all nav links
//         navLinks.forEach(link => {
//             const parent = link.parentElement;
//             const linkHref = link.getAttribute('href') || '';

//             // Handle sidebar (<li>) and mobile nav (<a>) active states
//             const elementToActivate = parent.tagName === 'LI' ? parent : link;

//             if (linkHref.endsWith(targetId)) {
//                 elementToActivate.classList.add('active');
//             } else {
//                 elementToActivate.classList.remove('active');
//             }
//         });
//     };

//     // const handleLinkClick = (targetId, clickedLink) => {
//     //     if (!targetId || !targetId.startsWith('#')) {
//     //         // If it's not a hash link, let the browser handle it (e.g., /terms)
//     //         return;
//     //     }

//     //     // Hide all page sections
//     //     pageSections.forEach(section => {
//     //         section.classList.add('hidden');
//     //     });

//     //     // Show the target section
//     //     const targetSection = document.querySelector(targetId);
//     //     if (targetSection) {
//     //         targetSection.classList.remove('hidden');
//     //     } else {
//     //         console.warn(`Navigation error: Section with ID '${targetId}' not found.`);
//     //     }

//     //     // Update active classes on all nav links
//     //     navLinks.forEach(link => {
//     //         // For sidebar, the parent <li> gets the 'active' class
//     //         if (link.parentElement.tagName === 'LI') {
//     //             if (link.getAttribute('href').endsWith(targetId)) {
//     //                 link.parentElement.classList.add('active');
//     //             } else {
//     //                 link.parentElement.classList.remove('active');
//     //             }
//     //         }
//     //         // For mobile nav, the <a> tag itself gets 'active'
//     //         else {
//     //              if (link.getAttribute('href').endsWith(targetId)) {
//     //                 link.classList.add('active');
//     //             } else {
//     //                 link.classList.remove('active');
//     //             }
//     //         }
//     //     });
//     // };

//     // Attach a single, unified event listener to all navigation links
//     navLinks.forEach(link => {
//         link.addEventListener('click', (e) => {
//             const href = link.getAttribute('href');

//             // Check if we are on a dashboard page and the link is a hash link
//             if (href && href.includes('#') && window.location.pathname.includes('dashboard')) {
//                 e.preventDefault(); // Prevent default link behavior ONLY on dashboard pages

//                 const targetId = new URL(link.href).hash;
//                 handleLinkClick(targetId, link);

//                 // Optional: Update URL in the address bar without reloading
//                 history.pushState(null, '', targetId);
//             }
//             // For all other cases (e.g., on the terms page), let the link navigate normally
//         });
//     });

//     // // Attach a single, unified event listener to all navigation links
//     // navLinks.forEach(link => {
//     //     link.addEventListener('click', (e) => {
//     //         const href = link.getAttribute('href');

//     //         // Check if it's a link meant for SPA navigation
//     //         if (href && href.includes('#')) {
//     //             e.preventDefault(); // Prevent default link behavior

//     //             // Extract the hash (e.g., #dashboard-section)
//     //             const targetId = new URL(link.href).hash;

//     //             handleLinkClick(targetId, link);

//     //             // Optional: Update URL in the address bar
//     //             history.pushState(null, '', targetId);
//     //         }
//     //     });
//     // });

//     // On initial page load, show the correct section based on the URL hash
//     if (window.location.pathname.includes('dashboard')) {
//         const currentHash = window.location.hash;
//         if (currentHash && document.querySelector(currentHash)) {
//             handleLinkClick(currentHash, document.querySelector(`a[href$="${currentHash}"]`));
//         } else if (pageSections.length > 0) {
//             // Default to showing the dashboard section if no hash is present
//             handleLinkClick('#dashboard-section', document.querySelector('a[href$="#dashboard-section"]'));
//         }
//     }
// }