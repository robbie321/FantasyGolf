document.addEventListener('DOMContentLoaded', function() {

    // --- Element Selectors ---
    const pageSections = document.querySelectorAll('.page-section');

    // Desktop Sidebar
    const sidebarLinks = document.querySelectorAll('.sidebar-nav a, .sidebar-footer a[href^="#"]');

    // Mobile Navigation
    const mobileNavLinks = document.querySelectorAll('.mobile-nav a.nav-item');
    const moreButton = document.getElementById('more-btn');
    const moreMenu = document.querySelector('.more-options-menu');
    const moreMenuOverlay = document.querySelector('.more-options-overlay');
    const closeMenuButton = document.getElementById('close-menu-btn');
    const moreMenuItems = document.querySelectorAll('.more-options-menu .menu-list a');
    const dashboardContent = document.querySelector('.dashboard-content');

     // --- Join League Modal Selectors ---
    const joinLeagueModalOverlay = document.getElementById('join-league-overlay');
    const openModalBtns = [
        document.getElementById('join-league-btn'),
        document.getElementById('join-league-btn-mobile')
    ];
    const closeModalBtns = [
        document.getElementById('modal-close-btn'),
        document.getElementById('modal-cancel-btn')
    ];
    const leagueCodeInput = document.getElementById('league-code')
    const joinLeagueSubmitBtn = document.getElementById('join-league-submit-btn');
    const joinLeagueForm = document.getElementById('join-league-form');
    const modalMessageContainer = document.getElementById('modal-message');



    // --- Core Navigation Logic ---
    const handleNavigation = (targetId) => {

        const leagueView = document.getElementById('league-view-section');
        if (leagueView) {
            leagueView.remove();
        }
        if (pageSections.length > 0) {
            pageSections.forEach(section => section.classList.add('hidden'));
            const targetSection = document.querySelector(targetId);
            if (targetSection) {
                targetSection.classList.remove('hidden');
                window.scrollTo(0, 0);
            }

            [...sidebarLinks, ...mobileNavLinks].forEach(link => {
                const parent = link.parentElement;
                if (parent && parent.tagName === 'LI') parent.classList.remove('active');
                if(link) link.classList.remove('active');

                const linkTarget = link.getAttribute('href');
                if (linkTarget && linkTarget === targetId) {
                    if (parent && parent.tagName === 'LI') parent.classList.add('active');
                    link.classList.add('active');
                }
            });

            const nav = document.querySelector('.mobile-nav');
            if (nav) {
                nav.style.transform = 'translateY(100%)';
                requestAnimationFrame(() => {
                    nav.style.transition = 'transform 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
                    nav.style.transform = 'translateY(0)';
                });
            }

            if (targetId === '#leaderboards-section') {
                const activeTab = document.querySelector('.leaderboard-tour-tabs .tab-button.active') || document.querySelector('.leaderboard-tour-tabs .tab-button');
                if (activeTab) activeTab.click();
            } else if (targetId === '#schedule-section') {
                const activeTab = document.querySelector('.schedule-tour-tabs .tab-button.active') || document.querySelector('.schedule-tour-tabs .tab-button');
                if (activeTab) activeTab.click();
            }
        }

        // Hide the "More Options" menu after navigation
        closeMoreMenu();
    };

    // --- Event Listeners ---
    // --- Attach Navigation Handlers only if on a multi-section page ---
    if (pageSections.length > 0) {
        [...sidebarLinks, ...mobileNavLinks, ...moreMenuItems].forEach(link => {
            if(link) {
                link.addEventListener('click', function(e) {
                    const targetId = this.getAttribute('href');
                    if (targetId && targetId.startsWith('#')) {
                        e.preventDefault();
                        handleNavigation(targetId);
                    }
                });
            }
        });
    }



    // --- "More Options" Menu Toggle Logic ---
    const openMoreMenu = () => {
        moreMenu.classList.add('open');
        moreMenuOverlay.classList.remove('hidden');
    };

    const closeMoreMenu = () => {
        moreMenu.classList.remove('open');
        moreMenuOverlay.classList.add('hidden');
    };

    if (moreButton) moreButton.addEventListener('click', openMoreMenu);
    if (closeMenuButton) closeMenuButton.addEventListener('click', closeMoreMenu);
    if (moreMenuOverlay) moreMenuOverlay.addEventListener('click', closeMoreMenu);

    // --- Join League Modal Logic ---
    const openJoinLeagueModal = () => {
        console.log("Attempting to open modal...");
        if (joinLeagueModalOverlay) {
            joinLeagueModalOverlay.classList.remove('hidden');
            console.log("Modal opened successfully.");
        } else {
            console.error("Error: Could not find the modal overlay element to open.");
        }
    };
    const closeJoinLeagueModal = () => {
        if (joinLeagueModalOverlay) {
            joinLeagueModalOverlay.classList.add('hidden');
        }
    };

    // Debugging: Check if the modal element itself was found
    if (!joinLeagueModalOverlay) {
        console.error("CRITICAL: The modal overlay with id 'join-league-overlay' was not found in the HTML.");
    }

    openModalBtns.forEach(btn => {
        if (btn) btn.addEventListener('click', openJoinLeagueModal);
    });
    closeModalBtns.forEach(btn => {
        if (btn) btn.addEventListener('click', closeJoinLeagueModal);
    });
    if (joinLeagueModalOverlay) {
        joinLeagueModalOverlay.addEventListener('click', function(e) {
            if (e.target === joinLeagueModalOverlay) {
                closeJoinLeagueModal();
            }
        });
    }

    // Attach submit listener to the form
    if (joinLeagueForm) {
        joinLeagueForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (!leagueCodeInput || !joinLeagueSubmitBtn || !modalMessageContainer) {
            console.error('Modal form elements not found! Check your HTML IDs.');
            return;
        }

         // Get the CSRF token from the meta tag in your HTML
        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

        const leagueCode = leagueCodeInput.value.trim();
        modalMessageContainer.textContent = '';
        modalMessageContainer.className = 'modal-message';

        if (!leagueCode) {
            modalMessageContainer.textContent = 'Please enter a league code.';
            modalMessageContainer.classList.add('error');
            return;
        }

        joinLeagueSubmitBtn.disabled = true;
        joinLeagueSubmitBtn.textContent = 'Joining...';

        try {
            // Send the code to the backend. The URL must match your Flask route.
            const response = await fetch('/league/join', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ league_code: leagueCode }),
            });

            const data = await response.json();

            if (response.ok) {
                modalMessageContainer.textContent = data.message || 'Success! Redirecting...';
                modalMessageContainer.classList.add('success');
                // Redirect on success
                setTimeout(() => {
                    window.location.href = data.redirect_url || '/user_dashboard';
                }, 1500);
            } else {
                modalMessageContainer.textContent = data.error || 'Invalid code or an error occurred.';
                modalMessageContainer.classList.add('error');
                joinLeagueSubmitBtn.disabled = false;
                joinLeagueSubmitBtn.textContent = 'Join League';
            }
        } catch (error) {
            console.error('Submission error:', error);
            modalMessageContainer.textContent = 'Could not connect to the server. Please try again.';
            modalMessageContainer.classList.add('error');
            joinLeagueSubmitBtn.disabled = false;
            joinLeagueSubmitBtn.textContent = 'Join League';
        }
            console.log("Join league form submitted.");
        });
    } else {
         console.error("CRITICAL: The form with id 'join-league-form' was not found. Form submission will not work.");
    }


    // --- Initial Page Load ---
    const setDefaultPage = () => {
        const activeSidebarLink = document.querySelector('.sidebar-nav li.active a');
        const initialSectionId = activeSidebarLink ? activeSidebarLink.getAttribute('href') : '#dashboard-section';
        handleNavigation(initialSectionId);
    };

    setDefaultPage();


     // --- Dashboard "My Leagues" Tab Functionality ---
    const dashboardPage = document.getElementById('dashboard-section');
    if (dashboardPage) {
        const leagueTabs = dashboardPage.querySelectorAll('.league-tabs .tab-button');
        const leaguesGrid = dashboardPage.querySelector('.leagues-grid');

        const renderLeagueCards = (leagues) => {
            if (!leaguesGrid) return;
            if (!leagues || leagues.length === 0) {
                leaguesGrid.innerHTML = '<p style="padding: 1rem; text-align: center;">No leagues in this category.</p>';
                return;
            }

            leaguesGrid.innerHTML = leagues.map(league => {
                let rankClass = '';
                if (league.rank === 1) {
                    rankClass = 'rank-gold';
                } else if (league.rank === 2) {
                    rankClass = 'rank-silver';
                } else if (league.rank === 3) {
                    rankClass = 'rank-bronze';
                } else {
                    rankClass = 'rank-standard';
                }
                const rankHTML = league.rank ? `<span class="rank-badge ${rankClass}">Rank #${league.rank}</span>` : '';
                const tourTagClass = league.tour.toLowerCase() === 'pga' ? 'tag-usa' : 'tag-euro';
                const statusTagClass = `tag-${league.status.toLowerCase()}`;

                return `
                    <div class="league-card">
                        <div class="card-header">
                            <div>
                               <h3>${league.name}</h3>
                               ${rankHTML}
                            </div>
                            <div class="tags">
                                <span class="tag ${tourTagClass}">${league.tour}</span>
                                <span class="tag ${statusTagClass}">${league.status}</span>
                            </div>
                        </div>
                        <div class="card-body">
                             <div class="info-item"><span class="label"><i class="fa-solid fa-dollar-sign"></i> Entry Fee</span><span class="value">${league.entryFee}</span></div>
                             <div class="info-item"><span class="label"><i class="fa-solid fa-user-group"></i> Entries</span><span class="value">${league.entries}</span></div>
                             <div class="info-item"><span class="label"><i class="fa-solid fa-gem"></i> Prize Pool</span><span class="value">${league.prizePool}</span></div>
                             <div class="info-item"><span class="label"><i class="fa-solid fa-calendar-day"></i> Ends</span><span class="value">${league.ends}</span></div>
                        </div>
                        <div class="card-footer">
                            <a class="view-leaderboard-btn" href="/league/${league.id}" data-league-id="${league.id}">View Leaderboard <i class="fa-solid fa-chevron-right"></i></a>
                        </div>
                    </div>
                `;
            }).join('');
        };

        leagueTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                leagueTabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                const tabText = tab.textContent.toLowerCase();
                if (tabText.includes('upcoming')) {
                    renderLeagueCards(upcomingLeaguesData);
                } else if (tabText.includes('past')) {
                    renderLeagueCards(pastLeaguesData);
                } else { // Live
                    renderLeagueCards(liveLeaguesData);
                }
            });
        });

        // Initial load
        if(leagueTabs.length > 0) {
            leagueTabs[0].click();
        }
    }

     // --- Event Delegation for dynamic content ---
    if (dashboardContent) {
        dashboardContent.addEventListener('click', function(e) {
            const leaderboardBtn = e.target.closest('.view-leaderboard-btn');
            if (leaderboardBtn) {
                e.preventDefault();
                const leagueId = leaderboardBtn.dataset.leagueId;
                loadLeagueView(leagueId);
                return;
            }

            const backBtn = e.target.closest('#back-to-dashboard-btn');
            if (backBtn) {
                e.preventDefault();
                handleNavigation('#dashboard-section');
                return;
            }
        });
    }

    // --- Functions to load and render the league view ---
    async function loadLeagueView(leagueId) {
         console.log(`%cloadLeagueView called with leagueId: ${leagueId}`, 'color: blue; font-weight: bold;');
        if (!dashboardContent) return;
        pageSections.forEach(section => section.classList.add('hidden'));

        // // Create and append a loading message
        // const loadingP = document.createElement('p');
        // loadingP.id = 'loading-league';
        // loadingP.style.textAlign = 'center';
        // loadingP.style.padding = '2rem';
        // loadingP.textContent = 'Loading League Details...';
        // dashboardContent.appendChild(loadingP);

        try {
            const response = await fetch(`/league/${leagueId}`);
            if (!response.ok) throw new Error('Could not load league data.');
            const data = await response.json();
            renderLeagueView(data);
        } catch (error) {
          const loadingMessage = document.getElementById('loading-league');
            if(loadingMessage) loadingMessage.remove();

            const errorDiv = document.createElement('div');
            errorDiv.id = 'league-view-section';
            errorDiv.innerHTML = `<p style="text-align:center; padding: 2rem; color: red;">${error.message}</p>`;
            dashboardContent.appendChild(errorDiv);
        }
    }

    function renderLeagueView(data) {
        const loadingMessage = document.getElementById('loading-league');
        if (!dashboardContent) return;

        const { league, leaderboard, user_entry } = data;

        const myTeamHTML = user_entry ? `
            <div class="player-card">
                <div class="player-image-placeholder">
                    <img src="/static/images/headshots/${user_entry.player1_dg_id}.png" alt="Headshot of ${user_entry.player1_name}" class="player-headshot-icon" onerror="this.parentElement.innerHTML = '<i class=\\'fa-regular fa-user\\'></i>';">
                </div>
                <p>${user_entry.player1_name}</p>
                <span class="player-badge">${user_entry.player1_score}</span>
            </div>
            <div class="player-card">
                <div class="player-image-placeholder">
                    <img src="/static/images/headshots/${user_entry.player2_dg_id}.png" alt="Headshot of ${user_entry.player2_name}" class="player-headshot-icon" onerror="this.parentElement.innerHTML = '<i class=\\'fa-regular fa-user\\'></i>';">
                </div>
                <p>${user_entry.player2_name}</p>
                <span class="player-badge">${user_entry.player2_score}</span>
            </div>
            <div class="player-card">
                <div class="player-image-placeholder">
                    <img src="/static/images/headshots/${user_entry.player3_dg_id}.png" alt="Headshot of ${user_entry.player3_name}" class="player-headshot-icon" onerror="this.parentElement.innerHTML = '<i class=\\'fa-regular fa-user\\'></i>';">
                </div>
                <p>${user_entry.player3_name}</p>
                <span class="player-badge">${user_entry.player3_score}</span>
            </div>
        ` : '<p>You do not have an entry in this league.</p>';

        const leaderboardRowsHTML = leaderboard.map(item => `
            <tr>
                <td>${item.rank}</td>
                <td>${item.user_name}</td>
                <td class="text-right score-under">${item.total_score}</td>
            </tr>
        `).join('');

        const leagueViewSection = document.createElement('div');
        leagueViewSection.id = 'league-view-section'; // Give it an ID for easy removal

        leagueViewSection.innerHTML = `
            <section class="page-section">
                <a href="#" class="back-link" id="back-to-dashboard-btn"><i class="fa-solid fa-arrow-left"></i> Back to Dashboard</a>
                <div class="page-header">
                    <h1>${league.name} <span class="tag tag-live">Live</span></h1>
                    <p class="subtitle">Your total score: ${user_entry ? user_entry.total_score : 'N/A'}</p>
                </div>
                <section class="my-team-section">
                    <h3>My Team</h3>
                    <div class="team-display-grid">
                        ${myTeamHTML}
                    </div>
                </section>
                <div class="leaderboard-table-container">
                    <table class="leaderboard-table">
                        <thead>
                            <tr>
                                <th>RANK</th>
                                <th>ENTRY NAME</th>
                                <th class="text-right">TOTAL SCORE</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${leaderboardRowsHTML}
                        </tbody>
                    </table>
                </div>
            </section>
        `;

        // Append the new view instead of replacing everything
        dashboardContent.appendChild(leagueViewSection);
    }


    // --- Tour Schedule Section Logic ---
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
    }

    async function loadScheduleData(tour) {
        const container = document.getElementById('schedule-list-container');
        if (!container) return;

        // if (scheduleCache[tour]) {
        //     renderSchedule(scheduleCache[tour]);
        //     console.log(`Loaded ${tour} schedule from cache.`);
        //     return;
        // }

        container.innerHTML = `<p style="text-align: center;">Loading ${tour} schedule...</p>`;
        try {
            const response = await fetch(`/api/tour-schedule/${tour}`);
            if (!response.ok) throw new Error('Network response was not ok');
            const schedule = await response.json();
            // scheduleCache[tour] = schedule;
            renderSchedule(schedule);
        } catch (error) {
            console.error(`Failed to fetch ${tour} schedule:`, error);
            container.innerHTML = `<p style="text-align: center;">Could not load schedule.</p>`;
        }
    }

    function renderSchedule(schedule) {
        const container = document.getElementById('schedule-list-container');
        if (!container) return;
        if (!schedule || schedule.length === 0) {
            container.innerHTML = '<p style="text-align: center;">No upcoming tournaments found.</p>';
            return;
        }

        // --- SORTING LOGIC ---
        // 1. Map the schedule to a new array that includes a parsed date and status
        const sortedSchedule = schedule.map(item => {
        const tournamentStartDate = new Date(item.start_date);
            return {
                ...item, // Keep all original item data
                startDateObj: tournamentStartDate,
                status: tournamentStartDate < serverTimeNow ? 'completed' : 'upcoming'
            };
        }).sort((a, b) => {
            // 2. Sort the new array
            if (a.status === 'upcoming' && b.status === 'completed') {
                return -1; // 'a' (upcoming) comes before 'b' (completed)
            }
            if (a.status === 'completed' && b.status === 'upcoming') {
                return 1; // 'b' (upcoming) comes before 'a' (completed)
            }

            // If both are upcoming, sort by the soonest date
            if (a.status === 'upcoming') {
                return a.startDateObj - b.startDateObj; // Ascending order
            }

            // If both are completed, sort by the most recent date
            if (a.status === 'completed') {
                return b.startDateObj - a.startDateObj; // Descending order
            }

            return 0;
        });

        container.innerHTML = sortedSchedule.map(item =>{
            // 1. Convert the tournament's start_date string into a JavaScript Date object

        // 2. Perform the date comparison
        const statusTag = `<span class="status-tag ${item.status}">${item.status.toUpperCase()}</span>`;

        return  `
            <div class="schedule-item">
                <div class="schedule-details">
                    <div class="schedule-title">
                        <strong>${item.event_name}</strong>
                        ${statusTag}
                    </div>
                    <span><strong>Course:</strong> ${item.course} <strong>Date:</strong> ${item.start_date} <strong>Location:</strong> ${item.location}</span>
                </div>

            </div>
        `;

        }).join('');
    }

    // <div class="schedule-actions">
    //                  <button class="btn-icon"><i class="fa-regular fa-calendar-plus"></i> Add to Calendar</button>
    //                  <button class="btn btn-outline-sm">View Details</button>
    //             </div>


     // --- Tour Leaderboards Section Logic ---
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
    }

    /**
     * Fetches live tournament data from your Flask API.
     * @param {string} tour - The tour to fetch data for (e.g., 'PGA').
     */
    async function loadLeaderboardData(tour) {
        const tableBody = document.querySelector('#leaderboards-section .leaderboard-table tbody');
        if (!tableBody) return;

        // 1. Show a loading message
        tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Loading live stats...</td></tr>';

        try {
            // 2. Call your new Flask API endpoint
            const response = await fetch(`/api/live-leaderboard/${tour}`);

            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }

            const stats = await response.json();

            // 3. Call a function to render the data
            renderLeaderboard(stats);

        } catch (error) {
            console.error("Failed to fetch leaderboard stats:", error);
            tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Could not load leaderboard data.</td></tr>';
        }
    }

    /**
     * Renders the leaderboard data into the HTML table.
     * @param {Array} stats - An array of player stat objects.
     */
    function renderLeaderboard(stats) {
        const tableBody = document.querySelector('#leaderboards-section .leaderboard-table tbody');
        if (!tableBody) return;

        if (!stats || stats.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No live stats available for this tour.</td></tr>';
            return;
        }

        // 4. Create the HTML for each player row
        const rowsHTML = stats.map((player, index) => `
            <tr class="${index === 0 ? 'highlighted' : ''}">
                <td>${player.current_pos || 'N/A'}</td>
                <td><span class="flag"></span> ${player.player_name || 'Unknown Player'}</td>
                <td class="score-under">${player.current_score || 0}</td>
                <td>${player.thru || 'F'}</td>
                <td class="score-under">${player.today || 0}</td>
                <td>-</td>
            </tr>
        `).join('');

        // 5. Update the table with the new rows
        tableBody.innerHTML = rowsHTML;
    }




    // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    // --- NEW: DYNAMIC PLAYER CARD LOADING & FILTERING ---
    // ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    // 1. Mock Data (replace this with a real fetch call to your server)
    const players_data = [
        {
            player: { dg_id: 1, fullName: 'Aaron Cockerill' },
            profile: { country: 'Canada', countryCode: '🇨🇦', proYear: 2015, wins: 3, winnings: '1.3M', rank: 140, status: 'Active' }
        },
        {
            player: { dg_id: 2, fullName: 'Aaron Rai' },
            profile: { country: 'England', countryCode: '🏴󠁧󠁢󠁥󠁮󠁧󠁿', proYear: 2012, wins: 2, winnings: '3.9M', rank: 87, status: 'Active' }
        },
        {
            player: { dg_id: 3, fullName: 'Adam Long' },
            profile: { country: 'USA', countryCode: '🇺🇸', proYear: 2010, wins: 1, winnings: '0.8M', rank: 112, status: 'Active' }
        },
        {
            player: { dg_id: 4, fullName: 'Adrian Otangui' },
            profile: null // Example of a player with no profile details
        },
        {
            player: { dg_id: 5, fullName: 'Shane Lowry' },
            profile: { country: 'Ireland', countryCode: '🇮🇪', proYear: 2009, wins: 6, winnings: '22.5M', rank: 31, status: 'Active' }
        }
    ];

    // 2. The function to generate and display player cards
    const loadPlayerCards = (players) => {
        const grid = document.querySelector('.player-profiles-grid');
        if (!grid) return;

        if (players.length === 0) {
            grid.innerHTML = '<p>No players found.</p>';
            return;
        }

        let cardsHTML = '';
        players.forEach(data => {
            const initials = data.player.fullName.split(' ').map(n => n[0]).join('');
            const imagePath = `https://placehold.co/150x150/e9ecef/212529?text=${initials}`;

            cardsHTML += `
                <div class="player-profile-card">
                    <div class="player-card-img">
                        <img src="{{ url_for('static', filename='images/headshots/' + data.player.dg_id|string + '.png') }}" alt="Headshot of {{ data.player.full_name() }}" class="player-headshot" onerror="this.style.display='none'">
                        ${data.profile.country ? `<span class="badge rank-badge">{{ data.profile.country }}</span>` : ''}
                        ${data.profile ? `<span class="badge status-badge active">${data.profile.status}</span>` : ''}
                    </div>
            `;

            if (data.profile) {
                cardsHTML += `
                    <h3>{{ data.player.full_name() }}</h3>
                    <p class="player-meta">{{ data.profile.country }} • Pro {{ data.profile.turned_pro or 'N/A' }}</p>
                    <a href="{{ url_for('player.single_player_profile', player_id=data.profile.id) }}" class="view-profile-link">View Full Profile →</a>
                `;
            } else {
                 cardsHTML += `
                    <h3>{{ data.player.full_name() }}</h3>
                    <p class="no-details-text" style="margin-top: 1rem; color: var(--text-light);">Additional details not available.</p>
                `;
            }

            cardsHTML += '</div>';
        });

        grid.innerHTML = cardsHTML;
    };

    // 3. Search filter functionality
    const searchInput = document.getElementById('player-search-input');
    const tableBody = document.getElementById("players-table-body");
    // const playerRows = tableBody.getElementsByTagName("tr");
    if (searchInput) {
        searchInput.addEventListener('keyup', (e) => {
            const searchTerm = searchInput.value.toLowerCase();

      // Loop through all the rows in the table
      for (let i = 0; i < playerRows.length; i++) {
        const row = playerRows[i];
        const playerNameCell = row.cells[0];

        if (playerNameCell) {
          const playerName = playerNameCell.textContent.toLowerCase();
          // If the player's name includes the search term, show the row
          if (playerName.includes(searchTerm)) {
            row.style.display = ""; // An empty string resets the display to its default
          } else {
            // Otherwise, hide it
            row.style.display = "none";
          }
        }
      }
        });
    }

    // 4. Initial load of all players
    loadPlayerCards(players_data);



    console.log("Fantasy Golf Dashboard scripts loaded with mobile navigation.");
});