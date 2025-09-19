/**
 * ui.js - UI Component Management
 * Handles interactive UI elements like modals and menus.
 */
import { joinLeague } from './api.js';

export function setupModalHandlers() {
    // --- Selectors ---

    const joinLeagueOverlay = document.getElementById('join-league-overlay');
    const openModalBtns = [document.getElementById('join-league-btn'), document.getElementById('join-league-btn-mobile')];
    const closeModalBtns = [document.getElementById('modal-close-btn'), document.getElementById('modal-cancel-btn')];
    const joinLeagueForm = document.getElementById('join-league-form');
    const leagueCodeInput = document.getElementById('league-code');
    const joinLeagueSubmitBtn = document.getElementById('join-league-submit-btn');
    const modalMessageContainer = document.getElementById('modal-message');

    // --- Get Elements ---
    const userMenuButton = document.querySelector('.user-menu-button');
    const userDropdown = document.querySelector('.user-dropdown');

    // Mobile Side Menu Elements
    const mobileMoreBtn = document.getElementById('more-btn'); // The button in the mobile nav
    const moreOptionsMenu = document.querySelector('.more-options-menu');
    const moreOptionsOverlay = document.querySelector('.more-options-overlay');
    const closeOptionsMenuBtn = document.getElementById('close-menu-btn');
    const optionsMenuLinks = document.querySelectorAll('.more-options-menu .menu-list a');


    const openModal = () => {
    // This now matches your CSS by removing the 'hidden' class
        if (joinLeagueOverlay) joinLeagueOverlay.classList.remove('hidden');
    };

    const closeModal = () => {
        // This now matches your CSS by adding the 'hidden' class
        if (joinLeagueOverlay) joinLeagueOverlay.classList.add('hidden');
    };

    openModalBtns.forEach(btn => {
        if (btn) btn.addEventListener('click', (e) => {
            e.preventDefault();
            openModal();
        });
    });

    closeModalBtns.forEach(btn => {
        if (btn) btn.addEventListener('click', closeModal);
    });

    // Close modal if user clicks on the overlay itself
    if (joinLeagueOverlay) {
        joinLeagueOverlay.addEventListener('click', (e) => {
            // We check if the click is on the overlay and not the modal itself
            if (e.target === joinLeagueOverlay) {
                closeModal();
            }
        });
    }

    if (joinLeagueForm) {
        joinLeagueForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            // const leagueCode = leagueCodeInput.value.trim();
            // const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

            joinLeagueSubmitBtn.disabled = true;
            joinLeagueSubmitBtn.textContent = 'Joining...';
            modalMessageContainer.textContent = '';

            // Safely get the CSRF token
            const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
            if (!csrfTokenMeta) {
                modalMessageContainer.textContent = 'Error: Security token not found. Please refresh the page.';
                modalMessageContainer.className = 'modal-message error';
                joinLeagueSubmitBtn.textContent = 'Join League';
                joinLeagueSubmitBtn.disabled = false;
                return;
            }
            const csrfToken = csrfTokenMeta.getAttribute('content');
            const leagueCode = leagueCodeInput.value;

            try {
                const result = await joinLeague(leagueCode, csrfToken);

                if (result.success) {
                    modalMessageContainer.textContent = 'Successfully joined league! Redirecting...';
                    modalMessageContainer.className = 'modal-message success';
                    // Redirect to the league page after a short delay
                    setTimeout(() => {
                        window.location.href = result.redirect_url;
                    }, 1500);
                } else {
                    modalMessageContainer.textContent = result.message || 'An unknown error occurred.';
                    modalMessageContainer.className = 'modal-message error';
                    joinLeagueSubmitBtn.textContent = 'Join League';
                    joinLeagueSubmitBtn.disabled = false;
                }
            } catch (error) {
                modalMessageContainer.textContent = 'A network error occurred. Please try again.';
                modalMessageContainer.className = 'modal-message error';
                joinLeagueSubmitBtn.textContent = 'Join League';
                joinLeagueSubmitBtn.disabled = false;
            }
        });
    }


    // --- Landing Page "Join with Code" Form Logic ---
    const landingJoinForm = document.getElementById('landing-join-form');
    if (landingJoinForm) {
        landingJoinForm.addEventListener('submit', (e) => {
            e.preventDefault(); // Prevent the form from submitting normally
            const landingCodeInput = document.getElementById('league-code-landing');
            const leagueCode = landingCodeInput.value.trim();

            if (leagueCode) {
                // Redirect to the login page, passing the code as a query parameter
                window.location.href = `/auth/login_choice?code=${leagueCode}`;
            } else {
                const landingMessage = document.getElementById('landing-form-message');
                landingMessage.textContent = 'Please enter a league code.';
                landingMessage.style.color = 'var(--text-red)';
            }
        });
    }


    // --- User Dropdown Menu (Desktop) ---
    if (userMenuButton && userDropdown) {
        userMenuButton.addEventListener('click', (e) => {
            e.stopPropagation();
            userDropdown.classList.toggle('active');
        });
    }

    // --- Mobile "More Options" Side Menu ---
    const openOptionsMenu = () => {
        if (moreOptionsMenu && moreOptionsOverlay) {
            moreOptionsMenu.classList.add('open'); // Slides the menu in
            moreOptionsOverlay.classList.remove('hidden'); // Shows the overlay
        }
    };
    const closeOptionsMenu = () => {
        if (moreOptionsMenu && moreOptionsOverlay) {
            moreOptionsMenu.classList.remove('open'); // Slides the menu out
            moreOptionsOverlay.classList.add('hidden'); // Hides the overlay
        }
    };

    // Event listener for the mobile nav "More" button
    if (mobileMoreBtn) {
        mobileMoreBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            openOptionsMenu();
        });
    }

    // Event listener for the close button inside the menu
    if (closeOptionsMenuBtn) {
        closeOptionsMenuBtn.addEventListener('click', closeOptionsMenu);
    }

    // Event listener for the overlay to close the menu
    if (moreOptionsOverlay) {
        moreOptionsOverlay.addEventListener('click', closeOptionsMenu);
    }

    // Close the side menu when a navigation link inside it is clicked
    optionsMenuLinks.forEach(link => {
        // Don't close for the logout link, let it navigate
        if (!link.classList.contains('logout-link')) {
            link.addEventListener('click', closeOptionsMenu);
        }
    });

    // --- Close Menus when clicking outside of them ---
    document.addEventListener('click', (e) => {
        // Close desktop dropdown if clicking outside
        if (userDropdown && userDropdown.classList.contains('active')) {
            if (userMenuButton && !userMenuButton.contains(e.target) && !userDropdown.contains(e.target)) {
                userDropdown.classList.remove('active');
            }
        }
    });

    const loginPage = document.getElementById('login-page');
    if (loginPage) {
        const tabs = loginPage.querySelectorAll('.login-tab-button');
        const tabContents = loginPage.querySelectorAll('.login-tab-content');

        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                // Deactivate all tabs and content
                tabs.forEach(t => t.classList.remove('active'));
                tabContents.forEach(c => c.classList.remove('active'));

                // Activate the clicked tab and its content
                tab.classList.add('active');
                const target = document.querySelector(tab.dataset.tabTarget);
                if (target) {
                    target.classList.add('active');
                }
            });
        });
    }

    // --- Club Dashboard League Tabs Logic ---
    const clubLeagueTabsContainer = document.getElementById('club-league-tabs');
    if (clubLeagueTabsContainer) {
        const tabs = clubLeagueTabsContainer.querySelectorAll('.tab-button');
        const tableBody = document.getElementById('club-leagues-table').querySelector('tbody');

        const renderClubLeagues = (statusFilter) => {
            // Use the clubLeagues data made available globally from the template
            const leagues = window.clubLeagues || [];

            const filteredLeagues = leagues.filter(league => league.status === statusFilter);

            if (!tableBody) return;

            if (filteredLeagues.length === 0) {
                tableBody.innerHTML = `<tr><td colspan="4" class="text-center" style="padding: 2rem; background-color: var(--white); border-radius: var(--border-radius);">No ${statusFilter.toLowerCase()} leagues found.</td></tr>`;
                return;
            }

            tableBody.innerHTML = filteredLeagues.map(league => `
                <tr>
                    <td>
                        <strong>${league.name}</strong><br>
                        <small>Code: ${league.league_code}</small>
                    </td>
                    <td class="text-center">${league.entries}</td>
                    <td class="text-center">
                        <span class="tag tag-${league.status.toLowerCase()}">${league.status}</span>
                    </td>
                    <td class="text-right">
                        <a href="/club-view/${league.id}" class="btn btn-outline">View</a>
                    </td>
                </tr>
            `).join('');
        };

        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                renderClubLeagues(tab.dataset.status);
            });
        });

        // Initial render on page load: show the 'Live' tab by default
        renderClubLeagues('Live');
    }
}
