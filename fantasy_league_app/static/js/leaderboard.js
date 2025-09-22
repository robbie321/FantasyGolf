/**
 * leaderboard.js - Professional Tour Data Display
 * Handles fetching and displaying tour leaderboards, schedules, and player profiles.
 */

/**
 * Formats a golf score for display with professional styling.
 */
function formatScore(score) {
    if (score === 0) {
        return 'E';
    } else if (score > 0) {
        return `+${score}`;
    }
    return score;
}

/**
 * Gets the correct CSS class for a score with professional styling.
 */
function getScoreClass(score) {
    if (score === 0) {
        return 'score-even';
    } else if (score > 0) {
        return 'score-positive';
    }
    return 'score-negative';
}

export function setupLeaderboards() {
    // Tour Leaderboards Section Logic
    const leaderboardSection = document.getElementById('leaderboards-section');
    if (leaderboardSection) {
        const leaderboardTabs = leaderboardSection.querySelectorAll('.leaderboard-tour-tabs .tab-button');
        leaderboardTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                leaderboardTabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const tour = tab.dataset.tour;
                loadLeaderboardData(tour);
            });
        });
        if (leaderboardTabs.length > 0) {
            leaderboardTabs[0].click();
        }
    }

    // Player Profiles Section Logic
    const playerProfilesSection = document.getElementById('profiles-section');
    if (playerProfilesSection) {
        setupPlayerSearch();
    }

    // Tour Schedule Section Logic
    const scheduleSection = document.getElementById('schedule-section');
    if (scheduleSection) {
        const scheduleTabs = scheduleSection.querySelectorAll('.schedule-tour-tabs .tab-button');
        scheduleTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                scheduleTabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const tour = tab.dataset.tour;
                loadScheduleData(tour);
            });
        });
        if (scheduleTabs.length > 0) {
            scheduleTabs[0].click();
        }
    }

    // Setup live leaderboard popup
    setupLiveLeaderboardPopup();

    // Setup collapsible leaderboard rows
    setupCollapsibleLeaderboard();
}

// ===================================================================
// PROFESSIONAL LEADERBOARD FUNCTIONS
// ===================================================================

async function loadLeaderboardData(tour) {
    const tableBody = document.querySelector('#leaderboards-section .leaderboard-table tbody');
    if (!tableBody) return;

    // Professional loading state
    tableBody.innerHTML = `
        <tr>
            <td colspan="5" style="text-align:center; padding: 2rem;">
                <i class="fa-solid fa-spinner fa-spin" style="font-size: 1.5rem; color: var(--primary-green); margin-bottom: 0.5rem;"></i>
                <br>Loading live tournament data...
            </td>
        </tr>
    `;

    try {
        const response = await fetch(`/api/live-leaderboard/${tour}`);
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        const stats = await response.json();
        renderLeaderboard(stats);
    } catch (error) {
        console.error("Failed to fetch leaderboard stats:", error);
        tableBody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align:center; padding: 2rem;">
                    <i class="fa-solid fa-exclamation-triangle" style="font-size: 1.5rem; color: var(--text-red); margin-bottom: 0.5rem;"></i>
                    <br>Could not load leaderboard data.
                </td>
            </tr>
        `;
    }
}

function renderLeaderboard(stats) {
    const tableBody = document.querySelector('#leaderboards-section .leaderboard-table tbody');
    if (!tableBody) return;

    if (!stats || stats.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align:center; padding: 2rem;">
                    <i class="fa-solid fa-info-circle" style="font-size: 1.5rem; color: var(--text-muted); margin-bottom: 0.5rem;"></i>
                    <br>No live stats available for this tour.
                </td>
            </tr>
        `;
        return;
    }

    const rowsHTML = stats.map((player, index) => {
        const totalScore = player.current_score || 0;
        const todayScore = player.today || 0;
        const isLeader = index === 0;

        return `
            <tr class="${isLeader ? 'highlighted leader-row' : ''}">
                <td class="pos">
                    ${isLeader ? '<i class="fa-solid fa-crown" style="color: #ffd700; margin-right: 0.5rem;"></i>' : ''}
                    ${player.current_pos || index + 1}
                </td>
                <td class="player-name" style="text-align: left;">
                    <span class="flag"></span>
                    ${player.player_name || 'Unknown Player'}
                </td>
                <td class="score ${getScoreClass(totalScore)}" style="text-align: center; font-weight: 700;">
                    ${formatScore(totalScore)}
                </td>
                <td style="text-align: center; font-weight: 600;">
                    ${player.thru === 18 ? 'F' : (player.thru || 'F')}
                </td>
                <td class="score ${getScoreClass(todayScore)}" style="text-align: center; font-weight: 600;">
                    ${formatScore(todayScore)}
                </td>
            </tr>
        `;
    }).join('');

    tableBody.innerHTML = rowsHTML;
}

// ===================================================================
// PROFESSIONAL LIVE LEADERBOARD POPUP
// ===================================================================

function setupLiveLeaderboardPopup() {
    const viewBtn = document.getElementById("view-live-leaderboard-btn");
    if (!viewBtn) return;

    const overlay = document.getElementById("live-leaderboard-overlay");
    const closeBtn = document.getElementById("popup-close-btn");
    const leaderboardTable = document.querySelector(".live-leaderboard-table");
    const leaderboardBody = document.querySelector(".live-leaderboard-table tbody");
    const loadingState = document.querySelector(".loading-state");

    const openPopup = () => {
        if (overlay) {
            overlay.classList.add("active");
            document.body.style.overflow = "hidden";
        }
    };

    const closePopup = () => {
        if (overlay) {
            overlay.classList.remove("active");
            document.body.style.overflow = "";
        }
    };

    viewBtn.addEventListener("click", async () => {
        if (!leaderboardBody) return;

        // Show loading state
        if (loadingState) loadingState.style.display = "block";
        if (leaderboardTable) leaderboardTable.style.display = "none";
        openPopup();

        try {
            const tour = viewBtn.dataset.tour;
            const response = await fetch(`/api/live-leaderboard/${tour}`);
            if (!response.ok) throw new Error("Network response was not ok");

            const players = await response.json();
            leaderboardBody.innerHTML = "";

            if (players.length === 0) {
                leaderboardBody.innerHTML = `
                    <tr>
                        <td colspan="5" class="empty-message" style="text-align: center; padding: 2rem;">
                            <i class="fa-solid fa-satellite-dish" style="font-size: 2rem; margin-bottom: 1rem; color: var(--text-muted);"></i>
                            <br>Live data not available for this tournament.
                        </td>
                    </tr>
                `;
            } else {
                players.forEach((player, index) => {
                    const scoreText = formatScore(player.current_score || 0);
                    const scoreClass = getScoreClass(player.current_score || 0);
                    const thruText = player.thru === 18 ? "F" : (player.thru || "-");
                    const todayScore = formatScore(player.today || 0);
                    const isLeader = index === 0;

                    const row = `
                        <tr class="${isLeader ? 'leader-row' : ''}">
                            <td class="pos">
                                ${isLeader ? '<i class="fa-solid fa-crown" style="color: #ffd700; margin-right: 0.25rem;"></i>' : ''}
                                ${player.current_pos || index + 1}
                            </td>
                            <td class="player-name">${player.player_name}</td>
                            <td style="text-align:center">
                                <span class="live-score ${scoreClass}">${scoreText}</span>
                            </td>
                            <td style="text-align:center; font-weight:600">${thruText}</td>
                            <td style="text-align:center; font-weight:600">${todayScore}</td>
                        </tr>
                    `;
                    leaderboardBody.insertAdjacentHTML("beforeend", row);
                });
            }

            // Hide loading, show table
            if (loadingState) loadingState.style.display = "none";
            if (leaderboardTable) leaderboardTable.style.display = "table";

        } catch (error) {
            console.error("Failed to fetch live leaderboard:", error);
            leaderboardBody.innerHTML = `
                <tr>
                    <td colspan="5" class="error-message" style="text-align: center; padding: 2rem;">
                        <i class="fa-solid fa-exclamation-triangle" style="font-size: 2rem; margin-bottom: 1rem; color: var(--text-red);"></i>
                        <br>Unable to load live data. Please try again later.
                    </td>
                </tr>
            `;
            if (loadingState) loadingState.style.display = "none";
            if (leaderboardTable) leaderboardTable.style.display = "table";
        }
    });

    if (closeBtn) closeBtn.addEventListener("click", closePopup);
    if (overlay) {
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) closePopup();
        });
    }
}

// ===================================================================
// PROFESSIONAL COLLAPSIBLE LEADERBOARD
// ===================================================================

// function setupCollapsibleLeaderboard() {
//     const mainRows = document.querySelectorAll(".leaderboard-main-row");
//     mainRows.forEach((row) => {
//         row.addEventListener("click", () => {
//             const targetId = row.dataset.target;
//             const detailsRow = document.querySelector(targetId);
//             if (detailsRow) {
//                 const isOpen = row.classList.contains("is-open");

//                 // Close all other open rows for better UX
//                 document.querySelectorAll(".leaderboard-main-row.is-open").forEach(openRow => {
//                     if (openRow !== row) {
//                         openRow.classList.remove("is-open");
//                         const openTargetId = openRow.dataset.target;
//                         const openDetailsRow = document.querySelector(openTargetId);
//                         if (openDetailsRow) {
//                             openDetailsRow.classList.remove("is-open");
//                         }
//                     }
//                 });

//                 // Toggle current row
//                 row.classList.toggle("is-open");
//                 detailsRow.classList.toggle("is-open");
//             }
//         });
//     });
// }


function setupCollapsibleLeaderboard() {
    // Wait for leaderboard to be populated
    const checkAndSetup = () => {
        // Look for main leaderboard rows (not the details rows)
        const mainRows = document.querySelectorAll('.leaderboard-main-row');

        if (mainRows.length === 0) {
            // If no main rows found, retry after a short delay
            setTimeout(checkAndSetup, 100);
            return;
        }

        mainRows.forEach((row) => {
            // Skip if already set up
            if (row.dataset.collapsibleSetup) return;

            row.dataset.collapsibleSetup = 'true';
            row.style.cursor = 'pointer';

            // Add click event listener
            row.addEventListener('click', () => {
                const targetId = row.dataset.target;
                const detailsRow = document.querySelector(targetId);

                if (detailsRow) {
                    const isOpen = row.classList.contains('is-open');

                    // Close all other open rows for better UX
                    document.querySelectorAll('.leaderboard-main-row.is-open').forEach(openRow => {
                        if (openRow !== row) {
                            openRow.classList.remove('is-open');
                            const openTargetId = openRow.dataset.target;
                            const openDetailsRow = document.querySelector(openTargetId);
                            if (openDetailsRow) {
                                openDetailsRow.classList.remove('is-open');
                                openDetailsRow.style.display = 'none';
                            }
                        }
                    });

                    // Toggle current row
                    row.classList.toggle('is-open');
                    detailsRow.classList.toggle('is-open');

                    // Show/hide the details row
                    if (isOpen) {
                        detailsRow.style.display = 'none';
                    } else {
                        detailsRow.style.display = 'table-row';
                    }
                }
            });
        });
    };

    checkAndSetup();
}


// ===================================================================
// PROFESSIONAL PLAYER PROFILE FUNCTIONS
// ===================================================================

function setupPlayerSearch() {
    const searchInput = document.querySelector('#profiles-section .search-bar input');
    if (!searchInput) return;

    searchInput.addEventListener('input', debounce((e) => {
        const searchTerm = e.target.value.toLowerCase().trim();
        filterPlayerProfiles(searchTerm);
    }, 300));
}

function filterPlayerProfiles(searchTerm) {
    const profileCards = document.querySelectorAll('.player-profile-card');
    let visibleCount = 0;

    profileCards.forEach(card => {
        const playerName = card.querySelector('h3')?.textContent?.toLowerCase() || '';
        const playerMeta = card.querySelector('.player-meta')?.textContent?.toLowerCase() || '';

        const isVisible = playerName.includes(searchTerm) || playerMeta.includes(searchTerm);

        card.style.display = isVisible ? 'block' : 'none';
        if (isVisible) visibleCount++;
    });

    // Show no results message if needed
    const grid = document.querySelector('.player-profiles-grid');
    const noResults = grid?.querySelector('.no-results');

    if (visibleCount === 0 && searchTerm) {
        if (!noResults) {
            const noResultsDiv = document.createElement('div');
            noResultsDiv.className = 'no-results';
            noResultsDiv.innerHTML = `
                <div class="empty-content">
                    <i class="fa-solid fa-search"></i>
                    <h3>No players found</h3>
                    <p>Try adjusting your search terms.</p>
                </div>
            `;
            grid?.appendChild(noResultsDiv);
        }
    } else if (noResults) {
        noResults.remove();
    }
}

// ===================================================================
// PROFESSIONAL TOUR SCHEDULE FUNCTIONS
// ===================================================================

async function loadScheduleData(tour) {
    const container = document.getElementById('schedule-list-container');
    if (!container) return;

    // Professional loading state
    container.innerHTML = `
        <div class="loading-state">
            <i class="fa-solid fa-spinner fa-spin"></i>
            <p>Loading ${tour.toUpperCase()} schedule...</p>
        </div>
    `;

    try {
        const response = await fetch(`/api/tour-schedule/${tour}`);
        if (!response.ok) throw new Error('Network response was not ok');
        const schedule = await response.json();
        renderSchedule(schedule);
    }catch (error) {
        console.error("Failed to fetch schedule data:", error);
        container.innerHTML = `
            <div class="empty-content">
                <i class="fa-solid fa-exclamation-triangle"></i>
                <h3>Error loading schedule</h3>
                <p>Unable to load tournament schedule. Please try again later.</p>
            </div>
        `;
    }
}

function renderSchedule(schedule) {
    const container = document.getElementById('schedule-list-container');
    if (!container) return;

    if (!schedule || schedule.length === 0) {
        container.innerHTML = `
            <div class="empty-content">
                <i class="fa-solid fa-calendar-xmark"></i>
                <h3>No tournaments found</h3>
                <p>No upcoming tournaments are currently scheduled.</p>
            </div>
        `;
        return;
    }

    // Sort schedule with professional logic
    const sortedSchedule = schedule.map(item => {
        const startDateObj = new Date(item.start_date);
        const now = new Date();
        return {
            ...item,
            startDateObj,
            status: startDateObj < now ? 'completed' : 'upcoming'
        };
    }).sort((a, b) => {
        // Upcoming tournaments first, then completed
        if (a.status === 'upcoming' && b.status === 'completed') return -1;
        if (a.status === 'completed' && b.status === 'upcoming') return 1;

        // Within each category, sort by date
        if (a.status === 'upcoming') return a.startDateObj - b.startDateObj;
        if (a.status === 'completed') return b.startDateObj - a.startDateObj;

        return 0;
    });

    container.innerHTML = sortedSchedule.map(item => {
        const statusTag = `<span class="status-tag ${item.status}">${item.status.toUpperCase()}</span>`;
        const dateFormatted = item.startDateObj.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        });

        return `
            <div class="schedule-item">
                <div class="schedule-details">
                    <div class="schedule-title">
                        <strong>${item.event_name}</strong>
                        ${statusTag}
                    </div>
                    <div class="schedule-meta">
                        <span class="schedule-course">
                            <i class="fa-solid fa-golf-ball"></i>
                            ${item.course}
                        </span>
                        <span class="schedule-date">
                            <i class="fa-solid fa-calendar"></i>
                            ${dateFormatted}
                        </span>
                        <span class="schedule-location">
                            <i class="fa-solid fa-map-marker-alt"></i>
                            ${item.location}
                        </span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// ===================================================================
// PROFESSIONAL LEAGUE VIEW INITIALIZATION
// ===================================================================

export function initialiseLeagueView() {
    console.log("Initializing professional league view...");

    // Professional collapsible details logic
    const toggleButton = document.getElementById("details-toggle");
    const content = document.getElementById("details-content");

    if (toggleButton && content) {
        const buttonText = toggleButton.querySelector("span");
        const buttonArrow = toggleButton.querySelector(".arrow");

        toggleButton.addEventListener("click", function() {
            const isExpanded = toggleButton.getAttribute("aria-expanded") === "true";

            // Toggle state
            toggleButton.setAttribute("aria-expanded", !isExpanded);
            content.hidden = isExpanded;

            // Professional animation
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
        });
    }

    // Setup other league view components
    setupCollapsibleLeaderboard();
    setupLiveLeaderboardPopup();
}

// ===================================================================
// UTILITY FUNCTIONS
// ===================================================================

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}