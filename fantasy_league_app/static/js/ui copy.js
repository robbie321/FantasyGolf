
import { joinLeague } from './api.js';

export function setupModalHandlers() {
    // Professional Join League Modal
    const joinLeagueOverlay = document.getElementById('join-league-overlay');
    const openModalBtns = [
        document.getElementById('join-league-btn'),           // Nav button
        document.getElementById('join-league-hero-btn'),      // Hero button (NEW)
        document.getElementById('join-league-btn-mobile'),    // Mobile nav button
        document.getElementById('join-first-league-btn')
    ].filter(Boolean);

    const closeModalBtns = [
        document.getElementById('modal-close-btn'),
        document.getElementById('modal-cancel-btn')
    ].filter(Boolean);

    const joinLeagueForm = document.getElementById('join-league-form');
    const leagueCodeInput = document.getElementById('league-code');
    const joinLeagueSubmitBtn = document.getElementById('join-league-submit-btn');
    const modalMessageContainer = document.getElementById('modal-message');

    // Professional modal controls
    const openModal = () => {
        if (joinLeagueOverlay) {
            joinLeagueOverlay.classList.remove('hidden');
            joinLeagueOverlay.classList.add('active');
            document.body.style.overflow = 'hidden';

            // Clear previous form data
            if (leagueCodeInput) leagueCodeInput.value = '';
            if (modalMessageContainer) {
                modalMessageContainer.textContent = '';
                modalMessageContainer.className = 'modal-message';
            }
            if (joinLeagueSubmitBtn) {
                joinLeagueSubmitBtn.disabled = false;
                joinLeagueSubmitBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Join League';
            }
        }
    };

    const closeModal = () => {
        if (joinLeagueOverlay) {
            joinLeagueOverlay.classList.remove('active');
            joinLeagueOverlay.classList.add('hidden');
            document.body.style.overflow = '';
        }
    };

    // Attach event listeners
    openModalBtns.forEach(btn => {
        if (btn) btn.addEventListener('click', (e) => {
            e.preventDefault();
            openModal();
        });
    });

    closeModalBtns.forEach(btn => {
        if (btn) btn.addEventListener('click', closeModal);
    });

    // Close modal when clicking on overlay
    if (joinLeagueOverlay) {
        joinLeagueOverlay.addEventListener('click', (e) => {
            if (e.target === joinLeagueOverlay) {
                closeModal();
            }
        });
    }

    // Professional form submission
    if (joinLeagueForm) {
        joinLeagueForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            if (!leagueCodeInput || !joinLeagueSubmitBtn || !modalMessageContainer) {
                console.error('Required modal elements not found');
                return;
            }

            const leagueCode = leagueCodeInput.value.trim();

            // Clear previous messages
            modalMessageContainer.textContent = '';
            modalMessageContainer.className = 'modal-message';

            if (!leagueCode) {
                modalMessageContainer.textContent = 'Please enter a valid league code.';
                modalMessageContainer.classList.add('error');
                return;
            }

            // Update button state
            joinLeagueSubmitBtn.disabled = true;
            joinLeagueSubmitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Joining...';

            // Get CSRF token
            const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
            if (!csrfTokenMeta) {
                modalMessageContainer.textContent = 'Security error. Please refresh the page.';
                modalMessageContainer.classList.add('error');
                joinLeagueSubmitBtn.disabled = false;
                joinLeagueSubmitBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Join League';
                return;
            }

            const csrfToken = csrfTokenMeta.getAttribute('content');

            try {
                const result = await joinLeague(leagueCode, csrfToken);

                if (result.success) {
                    modalMessageContainer.textContent = 'Successfully joined! Redirecting...';
                    modalMessageContainer.classList.add('success');
                    joinLeagueSubmitBtn.innerHTML = '<i class="fa-solid fa-check"></i> Success!';

                    setTimeout(() => {
                        window.location.href = result.redirect_url || '/dashboard';
                    }, 1500);
                } else {
                    modalMessageContainer.textContent = result.message || 'Invalid league code or error occurred.';
                    modalMessageContainer.classList.add('error');
                    joinLeagueSubmitBtn.disabled = false;
                    joinLeagueSubmitBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Join League';
                }
            } catch (error) {
                console.error('Network error:', error);
                modalMessageContainer.textContent = 'Network error. Please try again.';
                modalMessageContainer.classList.add('error');
                joinLeagueSubmitBtn.disabled = false;
                joinLeagueSubmitBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Join League';
            }
        });
    }

    // Landing page join form (if present)
    const landingJoinForm = document.getElementById('landing-join-form');
    if (landingJoinForm) {
        landingJoinForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const landingCodeInput = document.getElementById('league-code-landing');
            const leagueCode = landingCodeInput.value.trim();

            if (leagueCode) {
                window.location.href = `/auth/login_choice?code=${leagueCode}`;
            } else {
                const landingMessage = document.getElementById('landing-form-message');
                if (landingMessage) {
                    landingMessage.textContent = 'Please enter a league code.';
                    landingMessage.style.color = 'var(--text-red)';
                }
            }
        });
    }

    // Club dashboard league tabs
    setupClubLeagueTabs();

    // Professional league tabs for user dashboard
    setupUserLeagueTabs();
}

function setupClubLeagueTabs() {
    const clubLeagueTabsContainer = document.getElementById('club-league-tabs');
    if (!clubLeagueTabsContainer) return;

    const tabs = clubLeagueTabsContainer.querySelectorAll('.tab-button');
    const tableRows = document.querySelectorAll('.league-row');
    const emptyRow = document.querySelector('.empty-leagues-row');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Update active tab
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Filter leagues by status
            const selectedStatus = tab.dataset.status;
            let visibleCount = 0;

            tableRows.forEach(row => {
                const rowStatus = row.dataset.status;
                if (rowStatus === selectedStatus) {
                    row.style.display = '';
                    visibleCount++;
                } else {
                    row.style.display = 'none';
                }
            });

            // Handle empty state
            if (emptyRow) {
                const emptyContent = emptyRow.querySelector('.empty-leagues-content');
                if (visibleCount === 0 && tableRows.length > 0) {
                    emptyRow.style.display = '';
                    if (emptyContent) {
                        emptyContent.querySelector('h4').textContent = `No ${selectedStatus.toLowerCase()} leagues`;
                        emptyContent.querySelector('p').textContent = `You don't have any ${selectedStatus.toLowerCase()} leagues at the moment.`;
                    }
                } else if (tableRows.length === 0) {
                    emptyRow.style.display = '';
                } else {
                    emptyRow.style.display = 'none';
                }
            }
        });
    });

    // Copy functionality for club dashboard
    document.querySelectorAll('.copy-btn').forEach(button => {
        button.addEventListener('click', function() {
            const targetInput = document.querySelector(this.dataset.target);
            if (targetInput) {
                targetInput.select();
                targetInput.setSelectionRange(0, 99999);

                try {
                    document.execCommand('copy');

                    const originalHTML = this.innerHTML;
                    this.innerHTML = '<i class="fa-solid fa-check"></i>';
                    this.classList.add('success');

                    setTimeout(() => {
                        this.innerHTML = originalHTML;
                        this.classList.remove('success');
                    }, 2000);
                } catch (err) {
                    console.error('Failed to copy text: ', err);
                }
            }
        });
    });
}

function setupUserLeagueTabs() {
    const leagueTabsContainer = document.getElementById('league-tabs');
    if (!leagueTabsContainer) return;

    const tabs = leagueTabsContainer.querySelectorAll('.tab-button');
    const leaguesGrid = document.getElementById('leagues-grid');
    const emptyState = document.getElementById('empty-state');

    // This will be handled by the dashboard-specific JavaScript in the HTML files
    // since it needs access to the league data from the server
}

// Professional settings form handling
export function setupSettingsHandlers() {
    const profileForm = document.querySelector('.profile-form');
    const notificationForm = document.querySelector('.notification-form');

    if (profileForm) {
        profileForm.addEventListener('submit', function(e) {
            const submitBtn = profileForm.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
            }
        });
    }

    if (notificationForm) {
        notificationForm.addEventListener('submit', function(e) {
            const submitBtn = notificationForm.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
            }
        });
    }

    // Enhanced form validation
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function() {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.classList.contains('btn-danger')) {
                submitBtn.disabled = true;
                const originalText = submitBtn.innerHTML;

                // Don't change text if it's already been changed
                if (!submitBtn.innerHTML.includes('spinner')) {
                    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
                }

                setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                }, 5000);
            }
        });
    });
}