/**
 * views.js - Dynamic View Rendering
 * Contains functions to build and display dynamic HTML content.
 */


// This is the single function that will be exported and called from main.js
export function setupViews() {
    const dashboardContent = document.querySelector('.dashboard-content');

    // --- Event Delegation for dynamically created buttons ---
    if (dashboardContent) {
        dashboardContent.addEventListener('click', function(e) {


            // Listener for "Back to Dashboard" button
            const backBtn = e.target.closest('#back-to-dashboard-btn');
            if (backBtn) {
                e.preventDefault();
                window.location.reload();
                return;
            }
        });
    }

    // --- "My Leagues" Tab Functionality ---
    const dashboardPage = document.getElementById('dashboard-section');
    if (dashboardPage) {
        const leagueTabs = dashboardPage.querySelectorAll('.league-tabs .tab-button');
        // const leaguesGrid = dashboardPage.querySelector('.leagues-grid');

        leagueTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                leagueTabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                const tabText = tab.textContent.toLowerCase();
                // ✅ FIX: Access the global data variables via the 'window' object
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
}


function renderLeagueCards(leagues) {
    const leaguesGrid = document.querySelector('.leagues-grid');
    if (!leaguesGrid) return;
    if (typeof leagues === 'undefined' || !leagues || leagues.length === 0) {
        leaguesGrid.innerHTML = '<p style="padding: 1rem; text-align: center;">No leagues in this category.</p>';
        return;
    }

    leaguesGrid.innerHTML = leagues.map(league => {
        let rankClass = 'rank-standard';
        if (league.rank === 1) rankClass = 'rank-gold';
        else if (league.rank === 2) rankClass = 'rank-silver';
        else if (league.rank === 3) rankClass = 'rank-bronze';

        const rankHTML = league.rank ? `<span class="rank-badge ${rankClass}">Rank #${league.rank}</span>` : '';
        const tourTagClass = league.tour && league.tour.toLowerCase() === 'pga' ? 'tag-usa' : 'tag-euro';
        const statusTagClass = league.status ? `tag-${league.status.toLowerCase()}` : 'tag-live';

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
                    <a class="view-leaderboard-btn" href="/view/${league.id}" data-league-id="${league.id}">View Leaderboard <i class="fa-solid fa-chevron-right"></i></a>
                </div>
            </div>
        `;
    }).join('');
}


// countdown timer on view league page
      const countdownElement = document.getElementById("countdown");
      if (countdownElement) {
        const deadline = new Date(
          countdownElement.dataset.deadline + "Z"
        ).getTime();
        const timer = setInterval(function () {
          const now = new Date().getTime();
          const distance = deadline - now;
          if (distance < 0) {
            clearInterval(timer);
            countdownElement.innerHTML =
              "<h3>The entry deadline has passed.</h3>";
            return;
          }
          const days = Math.floor(distance / (1000 * 60 * 60 * 24));
          const hours = Math.floor(
            (distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)
          );
          const minutes = Math.floor(
            (distance % (1000 * 60 * 60)) / (1000 * 60)
          );
          const seconds = Math.floor((distance % (1000 * 60)) / 1000);
          document.getElementById("days").innerText = String(days).padStart(
            2,
            "0"
          );
          document.getElementById("hours").innerText = String(hours).padStart(
            2,
            "0"
          );
          document.getElementById("minutes").innerText = String(
            minutes
          ).padStart(2, "0");
          document.getElementById("seconds").innerText = String(
            seconds
          ).padStart(2, "0");
        }, 1000);
      }


// --- Functions to load and render the league view ---
// async function loadLeagueView(leagueId) {
//     const dashboardContent = document.querySelector('.dashboard-content');
//     if (!dashboardContent) return;

//     document.querySelectorAll('.page-section').forEach(s => s.classList.add('hidden'));
//     dashboardContent.innerHTML = '<p style="text-align:center; padding: 2rem;">Loading League Details...</p>';

//     const result = await fetchLeagueData(leagueId);

//     if (result.success) {
//         renderLeagueView(result.data);
//     } else {
//         dashboardContent.innerHTML = `<p style="text-align:center; padding: 2rem; color: red;">${result.error}</p>`;
//     }
// }

// function renderLeagueView(data) {
//     const dashboardContent = document.querySelector('.dashboard-content');
//     const { league, leaderboard, user_entry } = data;

//     const myTeamHTML = user_entry ? `
//         <div class="player-card">
//             <div class="player-image-placeholder">
//                 <img src="/static/images/headshots/${user_entry.player1_dg_id}.png" alt="Headshot" class="player-headshot-icon" onerror="this.parentElement.innerHTML = '<i class=\\'fa-regular fa-user\\'></i>';">
//             </div>
//             <p>${user_entry.player1_name}</p>
//             <span class="player-badge">${user_entry.player1_score}</span>
//         </div>
//         <div class="player-card">
//             <div class="player-image-placeholder">
//                 <img src="/static/images/headshots/${user_entry.player2_dg_id}.png" alt="Headshot" class="player-headshot-icon" onerror="this.parentElement.innerHTML = '<i class=\\'fa-regular fa-user\\'></i>';">
//             </div>
//             <p>${user_entry.player2_name}</p>
//             <span class="player-badge">${user_entry.player2_score}</span>
//         </div>
//         <div class="player-card">
//             <div class="player-image-placeholder">
//                 <img src="/static/images/headshots/${user_entry.player3_dg_id}.png" alt="Headshot" class="player-headshot-icon" onerror="this.parentElement.innerHTML = '<i class=\\'fa-regular fa-user\\'></i>';">
//             </div>
//             <p>${user_entry.player3_name}</p>
//             <span class="player-badge">${user_entry.player3_score}</span>
//         </div>
//     ` : '<p>You do not have an entry in this league.</p>';

//     const leaderboardRowsHTML = leaderboard.map(item => `
//         <tr>
//             <td>${item.rank}</td>
//             <td>${item.user_name}</td>
//             <td class="text-right score-under">${item.total_score}</td>
//         </tr>
//     `).join('');

//     const newHTML = `
//         <div id="league-view-section">
//             <section class="page-section">
//                 <a href="../../templates/main/user_dashboard.html" class="back-link" id="back-to-dashboard-btn"><i class="fa-solid fa-arrow-left"></i> Back to Dashboard</a>
//                 <div class="page-header">
//                     <h1>${league.name} <span class="tag tag-live">Live</span></h1>
//                     <p class="subtitle">Your total score: ${user_entry ? user_entry.total_score : 'N/A'}</p>
//                 </div>
//                 <section class="my-team-section">
//                     <h3>My Team</h3>
//                     <div class="team-display-grid">
//                         ${myTeamHTML}
//                     </div>
//                 </section>
//                 <div class="leaderboard-table-container">
//                     <table class="leaderboard-table">
//                         <thead>
//                             <tr>
//                                 <th>RANK</th>
//                                 <th>ENTRY NAME</th>
//                                 <th class="text-right">TOTAL SCORE</th>
//                             </tr>
//                         </thead>
//                         <tbody>
//                             ${leaderboardRowsHTML}
//                         </tbody>
//                     </table>
//                 </div>
//             </section>
//         </div>
//     `;
//     dashboardContent.innerHTML = newHTML;
// }