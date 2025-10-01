// Player Analytics Module
class PlayerAnalytics {
    constructor() {
        this.currentPlayerId = null;
    }

    async showAnalytics(playerId, playerName, tour = 'pga') {
        this.currentPlayerId = playerId;

        // Update modal title
        document.getElementById('analytics-player-name').textContent = playerName;

        // Show modal
        const overlay = document.getElementById('player-analytics-overlay');
        overlay.classList.remove('hidden');
        overlay.classList.add('active');

        // Show loading, hide content
        document.getElementById('analytics-loading').style.display = 'flex';
        document.getElementById('analytics-content').style.display = 'none';

        // Fetch analytics data with tour parameter
        try {
            const response = await fetch(`/api/player-analytics/${playerId}?tour=${tour}`);
            const data = await response.json();
            console.log('Analytics data received:', data);

            if (data.error) {
                throw new Error(data.error);
            }

            this.renderAnalytics(data);

            // Hide loading, show content
            document.getElementById('analytics-loading').style.display = 'none';
            document.getElementById('analytics-content').style.display = 'block';

        } catch (error) {
            console.error('Failed to load analytics:', error);
            document.getElementById('analytics-loading').innerHTML = `
                <i class="fa-solid fa-exclamation-circle"></i>
                <p>Failed to load analytics data</p>
            `;
        }
    }

    renderAnalytics(data) {
        // Render Win Probabilities
        if (data.predictions) {
            document.getElementById('prob-win').textContent =
                `${data.predictions.win_prob?.toFixed(1) || '0.0'}%`;
            document.getElementById('prob-top5').textContent =
                `${data.predictions.top5_prob?.toFixed(1) || '0.0'}%`;
            document.getElementById('prob-top10').textContent =
                `${data.predictions.top10_prob?.toFixed(1) || '0.0'}%`;
            document.getElementById('prob-top20').textContent =
                `${data.predictions.top20_prob?.toFixed(1) || '0.0'}%`;
            document.getElementById('prob-cut').textContent =
                `${data.predictions.make_cut_prob?.toFixed(1) || '0.0'}%`;
        }



        // Render Skill Rankings
        if (data.skill_ratings) {
            this.renderSkillBar('overall', data.skill_ratings.overall);
            this.renderSkillBar('driving', data.skill_ratings.driving);
            this.renderSkillBar('approach', data.skill_ratings.approach);
            this.renderSkillBar('short', data.skill_ratings.short_game);
            this.renderSkillBar('putting', data.skill_ratings.putting);
        }

        if (data.fantasy_projections) {
            const fp = data.fantasy_projections;
            document.getElementById('fit-baseline').textContent =
                fp.proj_points_total ? `${fp.proj_points_total.toFixed(1)} pts` : 'N/A';
            document.getElementById('fit-field').textContent =
                fp.value ? `${fp.value.toFixed(2)}x` : 'N/A';
        }
    }

    renderSkillBar(skill, rank) {
        const rankElement = document.getElementById(`rank-${skill}`);
        const barElement = document.getElementById(`bar-${skill}`);

        if (!rank) {
            rankElement.textContent = 'N/A';
            barElement.style.width = '0%';
            return;
        }

        rankElement.textContent = `#${rank}`;

        // Convert rank to percentage (rank 1 = 100%, rank 300 = 0%)
        const percentage = Math.max(0, Math.min(100, 100 - (rank / 3)));
        barElement.style.width = `${percentage}%`;

        // Color based on rank
        if (rank <= 50) {
            barElement.style.background = 'linear-gradient(135deg, #16a34a 0%, #22c55e 100%)';
        } else if (rank <= 100) {
            barElement.style.background = 'linear-gradient(135deg, #eab308 0%, #fbbf24 100%)';
        } else {
            barElement.style.background = 'linear-gradient(135deg, #dc2626 0%, #ef4444 100%)';
        }
    }
}

// Initialize analytics instance
const playerAnalytics = new PlayerAnalytics();

// Expose functions to global scope (for inline onclick handlers)
window.showPlayerAnalytics = function(playerId, playerName, tour = 'pga') {
    playerAnalytics.showAnalytics(playerId, playerName, tour);
};

window.closeAnalyticsModal = function() {
    const overlay = document.getElementById('player-analytics-overlay');
    overlay.classList.remove('active');
    overlay.classList.add('hidden');
};

// Close on overlay click
document.addEventListener('DOMContentLoaded', () => {
    const overlay = document.getElementById('player-analytics-overlay');
    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                closeAnalyticsModal();
            }
        });
    }
});