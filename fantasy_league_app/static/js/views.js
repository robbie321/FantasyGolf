/**
 * views.js - Professional Dynamic View Rendering
 * Contains functions to build and display dynamic HTML content.
 */

export function setupViews() {
    const dashboardContent = document.querySelector('.dashboard-content');

    // Event delegation for dynamically created buttons
    if (dashboardContent) {
        dashboardContent.addEventListener('click', function(e) {
            // Handle back to dashboard button
            const backBtn = e.target.closest('#back-to-dashboard-btn');
            if (backBtn) {
                e.preventDefault();
                // Navigate back to dashboard section
                const dashboardSection = document.getElementById('dashboard-section');
                if (dashboardSection) {
                    document.querySelectorAll('.page-section').forEach(section => {
                        section.classList.add('hidden');
                    });
                    dashboardSection.classList.remove('hidden');
                }
                return;
            }

            // Handle view leaderboard buttons
            const leaderboardBtn = e.target.closest('.view-leaderboard-btn');
            if (leaderboardBtn) {
                e.preventDefault();
                const leagueId = leaderboardBtn.dataset.leagueId;
                if (leagueId) {
                    // Navigate to the actual league page instead of loading dynamically
                    window.location.href = `/league/${leagueId}`;
                }
                return;
            }
        });
    }

    // Professional countdown timer setup
    setupCountdownTimer();

    // Professional league details collapsible setup
    setupLeagueDetails();
}

/**
 * Professional countdown timer for league deadlines
 */
function setupCountdownTimer() {
    const countdownElement = document.getElementById("countdown");
    if (!countdownElement) return;

    const deadline = new Date(countdownElement.dataset.deadline + "Z").getTime();

    const updateCountdown = () => {
        const now = new Date().getTime();
        const distance = deadline - now;

        if (distance < 0) {
            clearInterval(timer);
            countdownElement.innerHTML = `
                <div class="countdown-expired">
                    <i class="fa-solid fa-clock"></i>
                    <h3>Entry Deadline Has Passed</h3>
                </div>
            `;
            return;
        }

        const days = Math.floor(distance / (1000 * 60 * 60 * 24));
        const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((distance % (1000 * 60)) / 1000);

        const daysEl = document.getElementById("days");
        const hoursEl = document.getElementById("hours");
        const minutesEl = document.getElementById("minutes");
        const secondsEl = document.getElementById("seconds");

        if (daysEl) daysEl.innerText = String(days).padStart(2, "0");
        if (hoursEl) hoursEl.innerText = String(hours).padStart(2, "0");
        if (minutesEl) minutesEl.innerText = String(minutes).padStart(2, "0");
        if (secondsEl) secondsEl.innerText = String(seconds).padStart(2, "0");
    };

    const timer = setInterval(updateCountdown, 1000);
    updateCountdown(); // Initial call
}

/**
 * Professional league details collapsible functionality
 */
function setupLeagueDetails() {
    const toggleButton = document.getElementById("details-toggle");
    const content = document.getElementById("details-content");

    if (!toggleButton || !content) return;

    const buttonText = toggleButton.querySelector("span");
    const buttonArrow = toggleButton.querySelector(".arrow");

    toggleButton.addEventListener("click", function() {
        const isExpanded = toggleButton.getAttribute("aria-expanded") === "true";

        // Toggle aria-expanded
        toggleButton.setAttribute("aria-expanded", !isExpanded);

        // Toggle content visibility with professional animation
        if (isExpanded) {
            content.style.maxHeight = "0px";
            content.style.opacity = "0";
            if (buttonText) buttonText.textContent = "View league details";
            if (buttonArrow) buttonArrow.style.transform = "rotate(0deg)";
        } else {
            content.style.maxHeight = content.scrollHeight + "px";
            content.style.opacity = "1";
            if (buttonText) buttonText.textContent = "Hide league details";
            if (buttonArrow) buttonArrow.style.transform = "rotate(180deg)";
        }

        // Hide/show content
        content.hidden = isExpanded;
    });
}

/**
 * Professional league card rendering function
 * Used by dashboard components that need to render league cards
 */
export function renderProfessionalLeagueCards(leagues, container) {
    if (!container) return;

    if (!leagues || leagues.length === 0) {
        container.innerHTML = `
            <div class="empty-content">
                <i class="fa-solid fa-trophy"></i>
                <h3>No leagues found</h3>
                <p>You haven't joined any leagues in this category yet.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = leagues.map(league => {
        // Determine rank badge styling
        let rankBadge = '';
        if (league.current_rank || league.rank) {
            const rank = league.current_rank || league.rank;
            let rankClass = 'rank-standard';
            let rankIcon = '';

            if (rank === 1) {
                rankClass = 'rank-gold';
                rankIcon = '<i class="fa-solid fa-crown"></i>';
            } else if (rank === 2) {
                rankClass = 'rank-silver';
                rankIcon = '<i class="fa-solid fa-medal"></i>';
            } else if (rank === 3) {
                rankClass = 'rank-bronze';
                rankIcon = '<i class="fa-solid fa-medal"></i>';
            }

            rankBadge = `
                <div class="rank-badge ${rankClass}">
                    ${rankIcon}
                    Rank #${rank}
                </div>
            `;
        }

        // Determine status styling
        const status = league.status || 'Live';
        let statusClass = '';
        let statusIcon = '';

        switch(status.toLowerCase()) {
            case 'live':
                statusClass = 'status-live';
                statusIcon = '<i class="fa-solid fa-circle"></i>';
                break;
            case 'upcoming':
                statusClass = 'status-upcoming';
                statusIcon = '<i class="fa-solid fa-clock"></i>';
                break;
            case 'completed':
            case 'past':
                statusClass = 'status-completed';
                statusIcon = '<i class="fa-solid fa-flag-checkered"></i>';
                break;
            default:
                statusClass = 'status-live';
                statusIcon = '<i class="fa-solid fa-circle"></i>';
        }

        // Format dates
        const startDate = league.start_date ? new Date(league.start_date).toLocaleDateString() : 'TBD';
        const endDate = league.end_date ? new Date(league.end_date).toLocaleDateString() : 'TBD';

        return `
            <a href="/league/${league.id}" class="dashboard-league-card">
                <div class="card-header">
                    <div class="card-title-group">
                        <h3 class="league-name">${league.name}</h3>
                        ${rankBadge}
                    </div>
                    <div class="status-and-tour">
                        <span class="tour-tag-small">${(league.tour || 'PGA').toUpperCase()}</span>
                        <span class="status-badge ${statusClass}">${statusIcon} ${status}</span>
                    </div>
                </div>

                <div class="card-info-grid">
                    <div class="info-item">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="12" y1="1" x2="12" y2="23"></line>
                            <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
                        </svg>
                        <div class="info-text">
                            <span class="label">Entry Fee</span>
                            <span class="value">€${parseFloat(league.entry_fee || league.entryFee || 0).toFixed(2)}</span>
                        </div>
                    </div>

                    <div class="info-item">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                            <circle cx="9" cy="7" r="4"></circle>
                            <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                        </svg>
                        <div class="info-text">
                            <span class="label">Participants</span>
                            <span class="value">${league.total_entries || league.entries || 0}</span>
                        </div>
                    </div>

                    <div class="info-item">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"></path>
                            <line x1="7" y1="7" x2="7.01" y2="7"></line>
                        </svg>
                        <div class="info-text">
                            <span class="label">Prize Pool</span>
                            <span class="value">€${parseFloat(league.prize_amount || league.prizePool || 0).toFixed(2)}</span>
                        </div>
                    </div>

                    <div class="info-item">
                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                            <line x1="16" y1="2" x2="16" y2="6"></line>
                            <line x1="8" y1="2" x2="8" y2="6"></line>
                            <line x1="3" y1="10" x2="21" y2="10"></line>
                        </svg>
                        <div class="info-text">
                            <span class="label">${status.toLowerCase() === 'upcoming' ? 'Starts' : 'Tournament'}</span>
                            <span class="value">${status.toLowerCase() === 'upcoming' ? startDate : `${startDate} - ${endDate}`}</span>
                        </div>
                    </div>
                </div>

                <div class="card-footer">
                    <span>
                        ${status.toLowerCase() === 'completed' || status.toLowerCase() === 'past' ? 'View Results' :
                          status.toLowerCase() === 'live' ? 'View Leaderboard' : 'View Details'}
                    </span>
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                </div>
            </a>
        `;
    }).join('');
}

/**
 * Professional empty state rendering
 */
export function renderEmptyState(container, type = 'leagues') {
    if (!container) return;

    const emptyStates = {
        leagues: {
            icon: 'fa-solid fa-trophy',
            title: 'No leagues found',
            description: 'You haven\'t joined any leagues yet.',
            actionText: 'Join Your First League',
            actionId: 'join-first-league-btn'
        },
        live: {
            icon: 'fa-solid fa-circle',
            title: 'No live leagues',
            description: 'You don\'t have any active leagues at the moment.',
            actionText: 'Join a League',
            actionId: 'join-league-btn'
        },
        upcoming: {
            icon: 'fa-solid fa-clock',
            title: 'No upcoming leagues',
            description: 'You haven\'t joined any upcoming tournaments yet.',
            actionText: 'Browse Leagues',
            actionId: 'browse-leagues-btn'
        },
        past: {
            icon: 'fa-solid fa-flag-checkered',
            title: 'No completed leagues',
            description: 'You haven\'t completed any leagues yet.',
            actionText: 'Join a League',
            actionId: 'join-league-btn'
        }
    };

    const state = emptyStates[type] || emptyStates.leagues;

    container.innerHTML = `
        <div class="empty-content">
            <i class="${state.icon}"></i>
            <h3>${state.title}</h3>
            <p>${state.description}</p>
            <button class="btn btn-primary" id="${state.actionId}">
                <i class="fa-solid fa-plus"></i>
                ${state.actionText}
            </button>
        </div>
    `;
}

/**
 * Professional loading state
 */
export function showLoadingState(container, message = 'Loading...') {
    if (!container) return;

    container.innerHTML = `
        <div class="loading-state">
            <i class="fa-solid fa-spinner fa-spin"></i>
            <p>${message}</p>
        </div>
    `;
}

/**
 * Professional error state
 */
export function showErrorState(container, message = 'Something went wrong') {
    if (!container) return;

    container.innerHTML = `
        <div class="error-state">
            <i class="fa-solid fa-exclamation-triangle"></i>
            <h3>Error</h3>
            <p>${message}</p>
            <button class="btn btn-outline" onclick="location.reload()">
                <i class="fa-solid fa-refresh"></i>
                Try Again
            </button>
        </div>
    `;
}