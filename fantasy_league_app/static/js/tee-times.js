// Tee Times JavaScript Module
export class TeeTimesManager {
    constructor() {
        this.currentTour = this.detectCurrentTour();
        this.init();
    }

    detectCurrentTour() {
        // Method 1: Check if there's an active tab already selected
        const activeTab = document.querySelector('.tee-times-tour-tabs .tab-button.active');
        if (activeTab && activeTab.dataset.tour) {
            return activeTab.dataset.tour;
        }

        // Method 2: Check for data attribute on the section
        const section = document.getElementById('tee-times-section');
        if (section && section.dataset.defaultTour) {
            return section.dataset.defaultTour;
        }

        // Method 3: Check URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        const tourParam = urlParams.get('tour');
        if (tourParam && ['pga', 'euro', 'kft', 'alt'].includes(tourParam.toLowerCase())) {
            return tourParam.toLowerCase();
        }

        // Method 4: Check user's last viewed tour (localStorage)
        const lastTour = localStorage.getItem('lastViewedTeeTimesTour');
        if (lastTour && ['pga', 'euro', 'kft', 'alt'].includes(lastTour)) {
            return lastTour;
        }

        // Method 5: Detect based on current day and time (smart default)
        const smartDefault = this.getSmartDefaultTour();
        if (smartDefault) {
            return smartDefault;
        }

        // Fallback: default to PGA
        return 'pga';
    }

    getSmartDefaultTour() {
        // Get current day and time in UTC
        const now = new Date();
        const utcDay = now.getUTCDay(); // 0 = Sunday, 6 = Saturday
        const utcHour = now.getUTCHours();

        // PGA Tour typically plays Thursday-Sunday
        // DP World Tour (European) also typically Thursday-Sunday but in different time zones

        // During tournament days (Thu-Sun), check which tour is more likely to be active
        if (utcDay >= 4 || utcDay === 0) { // Thursday (4) to Sunday (0)
            // European events typically finish earlier in the day (UTC)
            // If it's early morning UTC (European afternoon/evening), show Euro
            if (utcHour >= 12 && utcHour < 20) {
                return 'euro';
            }
            // If it's afternoon/evening UTC (American morning/afternoon), show PGA
            else if (utcHour >= 14 || utcHour < 4) {
                return 'pga';
            }
        }

        // Default to PGA during non-tournament days
        return 'pga';
    }

    init() {
        this.setupEventListeners();
        this.setInitialActiveTab();
        this.loadTeeTimes(this.currentTour);
    }

    setInitialActiveTab() {
        // Set the correct tab as active based on detected tour
        document.querySelectorAll('.tee-times-tour-tabs .tab-button').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.tour === this.currentTour) {
                btn.classList.add('active');
            }
        });
    }

    setupEventListeners() {
        // Tour tab switching
        document.querySelectorAll('.tee-times-tour-tabs .tab-button').forEach(button => {
            button.addEventListener('click', (e) => {
                this.handleTourSwitch(e.target.dataset.tour);
            });
        });

        // Refresh button
        const refreshBtn = document.getElementById('refresh-tee-times-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.loadTeeTimes(this.currentTour, true);
            });
        }
    }

    handleTourSwitch(tour) {
        // Update active tab
        document.querySelectorAll('.tee-times-tour-tabs .tab-button').forEach(btn => {
            btn.classList.remove('active');
        });
        event.target.classList.add('active');

        this.currentTour = tour;

        // Save user preference
        localStorage.setItem('lastViewedTeeTimesTour', tour);

        this.loadTeeTimes(tour);
    }

    async loadTeeTimes(tour, forceRefresh = false) {
        const container = document.getElementById('tee-times-list');
        const loading = document.getElementById('tee-times-loading');
        const empty = document.getElementById('tee-times-empty');

        // Show loading state
        loading.style.display = 'flex';
        container.style.display = 'none';
        empty.style.display = 'none';

        try {
            // Add cache-busting parameter if force refresh
            const url = forceRefresh
                ? `/api/tee-times/${tour}?t=${Date.now()}`
                : `/api/tee-times/${tour}`;

            const response = await fetch(url);
            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            // Update tournament info
            document.getElementById('tee-times-event-name').textContent = data.event_name;
            document.getElementById('tee-times-round').textContent = `Round ${data.current_round}`;

            // Render tee times
            if (data.tee_times && data.tee_times.length > 0) {
                this.renderTeeTimes(data.tee_times);
                container.style.display = 'block';
            } else {
                empty.style.display = 'flex';
            }

        } catch (error) {
            console.error('Failed to load tee times:', error);
            empty.querySelector('p').textContent = 'Failed to load tee times. Please try again.';
            empty.style.display = 'flex';
        } finally {
            loading.style.display = 'none';
        }
    }

    renderTeeTimes(teeTimesData) {
        const container = document.getElementById('tee-times-list');

        const html = teeTimesData.map(group => `
            <div class="tee-time-group">
                <div class="tee-time-header">
                    <div class="time-display">
                        <i class="fa-solid fa-clock"></i>
                        <span class="time">${this.formatTime(group.time)}</span>
                    </div>
                    <span class="player-count">${group.players.length} player(s)</span>
                </div>
                <div class="tee-time-players">
                    ${group.players.map(player => `
                        <div class="tee-time-player">
                            <div class="player-info">
                                <span class="player-name">
                                    ${this.getCountryFlag(player.country)}
                                    ${this.formatPlayerName(player.name)}
                                </span>
                                <span class="player-country">${player.country || ''}</span>
                            </div>
                            <div class="player-stats">
                                ${player.current_score !== null ? `
                                    <span class="player-score ${this.getScoreClass(player.current_score)}">
                                        ${this.formatScore(player.current_score)}
                                    </span>
                                ` : ''}
                                ${player.current_pos !== '-' ? `
                                    <span class="player-pos">${player.current_pos}</span>
                                ` : ''}
                                ${player.odds ? `
                                    <span class="player-odds">${Math.round(player.odds)}</span>
                                ` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `).join('');

        container.innerHTML = html;
    }

    getCountryFlag(countryCode) {
        // Map 3-letter codes to 2-letter ISO codes for flag-icons
        const countryMap = {
            'USA': 'us',
            'ENG': 'eng',
            'GBR': 'gb',
            'IRL': 'ie',
            'ESP': 'es',
            'FRA': 'fr',
            'GER': 'de',
            'ITA': 'it',
            'SWE': 'se',
            'NOR': 'no',
            'DEN': 'dk',
            'AUS': 'au',
            'NZL': 'nz',
            'RSA': 'za',
            'JPN': 'jp',
            'KOR': 'kr',
            'CAN': 'ca',
            'MEX': 'mx',
            'ARG': 'ar',
            'BRA': 'br',
            'CHI': 'cl',
            'COL': 'co',
            'IND': 'in',
            'CHN': 'cn',
            'NED': 'nl',
            'BEL': 'be',
            'SUI': 'ch',
            'AUT': 'at',
            'POL': 'pl',
            'FIN': 'fi',
            'POR': 'pt',
            'ZIM': 'zw',
        };

        if (!countryCode) return '';

        const code = countryMap[countryCode.toUpperCase()];
        return code ? `<span class="fi fi-${code} country-flag-icon"></span>` : '';
    }

    formatTime(time) {
        // Convert 24-hour time to 12-hour with AM/PM
        const [hours, minutes] = time.split(':');
        const hour = parseInt(hours);
        const ampm = hour >= 12 ? 'PM' : 'AM';
        const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
        return `${displayHour}:${minutes} ${ampm}`;
    }

    formatPlayerName(name) {
        // Format "Surname, Name" to "Name Surname"
        if (name.includes(',')) {
            const [surname, firstName] = name.split(',').map(s => s.trim());
            return `${firstName} ${surname}`;
        }
        return name;
    }

    formatScore(score) {
        if (score === 0) return 'E';
        if (score > 0) return `+${score}`;
        return score.toString();
    }

    getScoreClass(score) {
        if (score < 0) return 'score-under';
        if (score > 0) return 'score-over';
        return 'score-even';
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('tee-times-section')) {
        new TeeTimesManager();
    }
});