/**
 * leaderboard.js - Tour Data Display
 * Handles fetching and displaying tour leaderboards, schedules, and player profiles.
 */

// This is the single function that will be exported and called from main.js
/**
 * Formats a golf score for display.
 * - Negative scores are returned as is (e.g., -5).
 * - Zero is returned as 'E' (for Even).
 * - Positive scores are returned with a '+' sign (e.g., +2).
 * @param {number} score The player's score.
 * @returns {string} The formatted score string.
 */
function formatScore(score) {
    if (score === 0) {
        return 'E';
    } else if (score > 0) {
        return `+${score}`;
    }
    return score; // Returns negative numbers as they are
}

/**
 * Gets the correct CSS class for a score.
 * @param {number} score The player's score.
 * @returns {string} The CSS class for styling.
 */
function getScoreClass(score) {
    if (score === 0) {
        return 'score-even'; // Black color for Even
    } else if (score > 0) {
        return 'score-over'; // Green color for Over Par
    }
    return 'score-under'; // Default red/negative color
}

export function setupLeaderboards() {
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
        if (leaderboardTabs.length > 0) {
            leaderboardTabs[0].click();
        }
    }

    // --- Player Profiles Section Logic ---
    const playerProfilesSection = document.getElementById('player-profiles-section');
    if (playerProfilesSection && typeof players_data !== 'undefined') {
        loadPlayerCards(players_data);
    }

    // --- NEW: Tour Schedule Section Logic ---
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
        // Automatically click the first tab to load initial data
        if (scheduleTabs.length > 0) {
            scheduleTabs[0].click();
        }
    }
}


// ===================================================================
// LEADERBOARD FUNCTIONS
// ===================================================================


async function loadLeaderboardData(tour) {
    const tableBody = document.querySelector('#leaderboards-section .leaderboard-table tbody');
    if (!tableBody) return;
    tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Loading live stats...</td></tr>';
    try {
        const response = await fetch(`/api/live-leaderboard/${tour}`);
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        const stats = await response.json();
        renderLeaderboard(stats);
    } catch (error) {
        console.error("Failed to fetch leaderboard stats:", error);
        tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Could not load leaderboard data.</td></tr>';
    }
}

function renderLeaderboard(stats) {
    const tableBody = document.querySelector('#leaderboards-section .leaderboard-table tbody');
    if (!tableBody) return;
    if (!stats || stats.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No live stats available for this tour.</td></tr>';
        return;
    }
    const rowsHTML = stats.map((player, index) => {
        const totalScore = player.current_score || 0;
        const todayScore = player.today || 0;

        return `
        <tr class="${index === 0 ? 'highlighted' : ''}">
            <td>${player.current_pos || 'N/A'}</td>
            <td style = "text-align:left"><span class="flag"></span> ${player.player_name || 'Unknown Player'}</td>
            <td class="${getScoreClass(totalScore)}">${formatScore(totalScore)}</td>
            <td>${player.thru || 'F'}</td>
            <td class="${getScoreClass(todayScore)}">${formatScore(todayScore)}</td>
        </tr>
    `}).join('');

    tableBody.innerHTML = rowsHTML;
}


// --- Live Tournament Leaderboard Popup ---
      const viewBtn = document.getElementById("view-live-leaderboard-btn");
      if (viewBtn) {
        // Define all elements related to the popup
        const overlay = document.getElementById("live-leaderboard-overlay");
        const closeBtn = document.getElementById("popup-close-btn");
        const leaderboardBody = document.querySelector(
          "#live-leaderboard-body .live-leaderboard-table tbody"
        );

        // Define the helper functions BEFORE they are used
        const openPopup = () => {
          if (overlay) overlay.classList.add("active");
        };
        const closePopup = () => {
          if (overlay) overlay.classList.remove("active");
        };

        // Attach the main event listener
        viewBtn.addEventListener("click", async () => {
          if (!leaderboardBody) return;

          leaderboardBody.innerHTML =
            '<tr><td colspan="5" style="text-align:center;">Loading...</td></tr>';
          openPopup(); // Now this function is defined and can be called

          try {
            const tour = viewBtn.dataset.tour;
            const response = await fetch(`/api/live-leaderboard/${tour}`);
            if (!response.ok) throw new Error("Network response was not ok");

            const players = await response.json();
            leaderboardBody.innerHTML = ""; // Clear loading message

            if (players.length === 0) {
              leaderboardBody.innerHTML =
                '<tr><td colspan="5" style="text-align:center;">Live data not available for this tour.</td></tr>';
              return;
            }

            players.forEach((player) => {
              // --- Conditional Score Logic ---
              let scoreText = player.total;
              let rndScore = player.today;
              let scoreClass = "score-negative"; // Default to red for under par

              if (player.total === 0) {
                scoreText = "E";
                scoreClass = "score-even";
              } else if (player.total > 0) {
                scoreText = `+${player.total}`;
                scoreClass = "score-positive";
              }

              rndScore = player.today === 0 ? "E" : player.today;

              // Display 'F' if thru is 18, otherwise display the number
              const thruText = player.thru === 18 ? "F" : player.thru;

              const row = `
                            <tr>
                                <td class="pos">${player.current_pos}</td>
                                <td class="player-name">${player.player_name}</td>

                                <td style="text-align:center"> <span class="live-score ${scoreClass}">${player.current_score}</span></td>
                                <td style="text-align:center; font-weight:bold">${thruText}</td>
                                <td style="text-align:center; font-weight:bold; padding-right:8px">${rndScore}</td>
                            </tr>
                        `;
              leaderboardBody.insertAdjacentHTML("beforeend", row);
            });
          } catch (error) {
            console.error("Failed to fetch live leaderboard:", error);
            leaderboardBody.innerHTML =
              '<tr><td colspan="5" style="text-align:center;">Could not load live data.</td></tr>';
          }
        });

        // Attach listeners for closing the popup
        if (closeBtn) closeBtn.addEventListener("click", closePopup);
        if (overlay)
          overlay.addEventListener("click", (e) => {
            if (e.target === overlay) closePopup();
          });
      }


// --- Collapsible League Leaderboard Rows ---
      const mainRows = document.querySelectorAll(".leaderboard-main-row");
      mainRows.forEach((row) => {
        row.addEventListener("click", () => {
          const targetId = row.dataset.target;
          const detailsRow = document.querySelector(targetId);
          if (detailsRow) {
            row.classList.toggle("is-open");
            detailsRow.classList.toggle("is-open");
          }
        });
      });

      // --- Socket.IO for Live Page Reload ---
    //   var socket = io();
    //   socket.on("connect", function () {
    //     console.log("Socket.IO connected!");
    //   });
    //   socket.on("scores_updated", function (data) {
    //     var currentLeagueTour = "{{ league.tour }}";
    //     if (data.updated_tours.includes(currentLeagueTour)) {
    //       location.reload();
    //     }
    //   });




// ===================================================================
// PLAYER PROFILE CARD FUNCTIONS
// ===================================================================

const loadPlayerCards = (players) => {
    const grid = document.querySelector('.player-profiles-grid');
    if (!grid) return;
    if (!players || players.length === 0) {
        grid.innerHTML = '<p>No players found.</p>';
        return;
    }
    const cardsHTML = players.map(data => {
        const countryBadge = data.country ? `<span class="badge rank-badge">${data.country}</span>` : '';
        const statusBadge = data.status ? `<span class="badge status-badge active">${data.status}</span>` : '';
        let profileHTML;
        if (data.profileUrl) {
            profileHTML = `
                <h3>${data.fullName}</h3>
                <p class="player-meta">${data.country} • Pro ${data.turnedPro || 'N/A'}</p>
                <a href="${data.profileUrl}" class="view-profile-link">View Full Profile →</a>
            `;
        } else {
            profileHTML = `
                <h3>${data.fullName}</h3>
                <p class="no-details-text" style="margin-top: 1rem; color: var(--text-light);">Additional details not available.</p>
            `;
        }
        return `
            <div class="player-profile-card">
                <div class="player-card-img">
                    <img src="${data.imageUrl}" alt="Headshot of ${data.fullName}" class="player-headshot" onerror="this.style.display='none'">
                    ${countryBadge}
                    ${statusBadge}
                </div>
                ${profileHTML}
            </div>
        `;
    }).join('');
    grid.innerHTML = cardsHTML;
};


// ===================================================================
// NEW: TOUR SCHEDULE FUNCTIONS
// ===================================================================

async function loadScheduleData(tour) {
    const container = document.getElementById('schedule-list-container');
    if (!container) return;
    container.innerHTML = `<p style="text-align: center;">Loading ${tour} schedule...</p>`;
    try {
        const response = await fetch(`/api/tour-schedule/${tour}`);
        if (!response.ok) throw new Error('Network response was not ok');
        const schedule = await response.json();
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

    const sortedSchedule = schedule.map(item => {
        return {
            ...item,
            startDateObj: new Date(item.start_date),
            status: new Date(item.start_date) < serverTimeNow ? 'completed' : 'upcoming'
        };
    }).sort((a, b) => {
        if (a.status === 'upcoming' && b.status === 'completed') return -1;
        if (a.status === 'completed' && b.status === 'upcoming') return 1;
        if (a.status === 'upcoming') return a.startDateObj - b.startDateObj;
        if (a.status === 'completed') return b.startDateObj - a.startDateObj;
        return 0;
    });

    container.innerHTML = sortedSchedule.map(item => {
        const statusTag = `<span class="status-tag ${item.status}">${item.status.toUpperCase()}</span>`;
        return `
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

export function initialiseLeagueView(){

        // --- Collapsible Details Logic ---
      console.log("Setting up collapsible details..."); // Log #1
      const toggleButton = document.getElementById("details-toggle");
      const content = document.getElementById("details-content");

      // Log #2: Check if the button and content elements were found
      console.log("Toggle Button element:", toggleButton);
      console.log("Content Div element:", content);
      const buttonText = toggleButton.querySelector("span");
      const buttonArrow = toggleButton.querySelector(".arrow");

      if (toggleButton && content) {
        // Log #3: Confirm that the elements were found and the listener will be attached
        console.log("Button and content found. Attaching click listener...");

        toggleButton.addEventListener("click", function () {
          // Log #4: This will appear ONLY when the button is successfully clicked
          console.log("Details button CLICKED!");

          const isExpanded =
            toggleButton.getAttribute("aria-expanded") === "true";
          toggleButton.setAttribute("aria-expanded", !isExpanded);
          content.hidden = isExpanded;

          // Log #5: Check the state after the click
          console.log(`Content is now hidden: ${isExpanded}`);
        });
      } else {
        // Log #6: This will show if one or both elements are missing
        console.error(
          "CRITICAL: Could not find the toggle button or the content div."
        );
      }

      if (toggleButton) {
        toggleButton.addEventListener("click", function () {
          // Check if the content is currently open
          const isOpen =
            content.style.maxHeight && content.style.maxHeight !== "0px";

          if (isOpen) {
            content.style.maxHeight = "0px";
            buttonText.textContent = "View league details";
            buttonArrow.style.transform = "rotate(0deg)";
          } else {
            // Set max-height to the content's scroll height to make it expand
            content.style.maxHeight = content.scrollHeight + "px";
            buttonText.textContent = "Hide league details";
            buttonArrow.style.transform = "rotate(180deg)";
          }
        });
      }

}