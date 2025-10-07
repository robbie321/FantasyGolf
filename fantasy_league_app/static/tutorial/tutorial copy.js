/**
 * Tutorial System for Fantasy Fairways
 * Provides interactive tutorials for new users
 */

class TutorialManager {
    constructor() {
        this.currentStep = 0;
        this.isActive = false;
        this.tutorials = this.getTutorialDefinitions();
    }

    getTutorialDefinitions() {
        return {
            dashboard: {
                id: 'dashboard',
                name: 'Dashboard Tour',
                steps: [
                    {
                        element: '.live-leagues-section',
                        title: 'Your Active Leagues',
                        content: 'Here you can see all your currently active leagues and track their progress in real-time.',
                        position: 'bottom'
                    },
                    {
                        element: '.upcoming-leagues-section',
                        title: 'Upcoming Leagues',
                        content: 'View leagues you\'ve joined that haven\'t started yet. Make sure to complete your team selection before the deadline!',
                        position: 'bottom'
                    },
                    {
                        element: '#leaderboards-section',
                        title: 'Live Leaderboards',
                        content: 'Track live tournament scores and see how your picks are performing against the field.',
                        position: 'top'
                    }
                ]
            },
            leagueEntry: {
                id: 'leagueEntry',
                name: 'Team Selection',
                steps: [
                    {
                        element: '.player-bucket',
                        title: 'Select Your Players',
                        content: 'Choose 3 players from the available pool. Balance star players with value picks for the best chance to win!',
                        position: 'right'
                    },
                    {
                        element: '.odds-display',
                        title: 'Player Odds',
                        content: 'Lower odds indicate favorites. Mix different odds levels to create a balanced team.',
                        position: 'left'
                    },
                    {
                        element: '.tiebreaker-input',
                        title: 'Tiebreaker',
                        content: 'Enter your prediction for the tiebreaker question. This determines the winner if scores are tied!',
                        position: 'top'
                    }
                ]
            }
        };
    }

    /**
     * Start a specific tutorial
     */
    async startTutorial(tutorialId) {
        const tutorial = this.tutorials[tutorialId];
        if (!tutorial) {
            console.error(`Tutorial ${tutorialId} not found`);
            return;
        }

        // Check if user has completed this tutorial
        try {
            const response = await fetch('/api/onboarding/status');
            const data = await response.json();

            if (data.tutorial_completed) {
                // User has completed tutorials, ask if they want to replay
                const replay = confirm('You\'ve already completed this tutorial. Would you like to see it again?');
                if (!replay) return;
            }
        } catch (error) {
            console.error('Error checking tutorial status:', error);
        }

        this.isActive = true;
        this.currentStep = 0;
        this.showStep(tutorial.steps[0]);
    }

    /**
     * Show a tutorial step
     */
    showStep(step) {
        // Remove any existing tutorial overlay
        this.removeTutorialOverlay();

        const element = document.querySelector(step.element);
        if (!element) {
            console.warn(`Element ${step.element} not found, skipping step`);
            return;
        }

        // Create overlay
        const overlay = document.createElement('div');
        overlay.className = 'tutorial-overlay';
        overlay.innerHTML = `
            <div class="tutorial-backdrop"></div>
            <div class="tutorial-spotlight"></div>
            <div class="tutorial-tooltip" data-position="${step.position}">
                <div class="tutorial-tooltip-header">
                    <h3>${step.title}</h3>
                    <button class="tutorial-close-btn" onclick="window.tutorialManager.endTutorial()">
                        <i class="fa-solid fa-times"></i>
                    </button>
                </div>
                <div class="tutorial-tooltip-content">
                    <p>${step.content}</p>
                </div>
                <div class="tutorial-tooltip-footer">
                    <button class="tutorial-btn tutorial-btn-secondary" onclick="window.tutorialManager.skipTutorial()">
                        Skip Tutorial
                    </button>
                    <div class="tutorial-nav-buttons">
                        ${this.currentStep > 0 ? '<button class="tutorial-btn" onclick="window.tutorialManager.previousStep()">Previous</button>' : ''}
                        <button class="tutorial-btn tutorial-btn-primary" onclick="window.tutorialManager.nextStep()">
                            ${this.currentStep === this.getCurrentTutorial().steps.length - 1 ? 'Finish' : 'Next'}
                        </button>
                    </div>
                </div>
                <div class="tutorial-progress">
                    Step ${this.currentStep + 1} of ${this.getCurrentTutorial().steps.length}
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        // Position the spotlight on the element
        this.positionSpotlight(element);
        this.positionTooltip(element, step.position);
    }

    positionSpotlight(element) {
        const spotlight = document.querySelector('.tutorial-spotlight');
        const rect = element.getBoundingClientRect();

        spotlight.style.top = `${rect.top - 10}px`;
        spotlight.style.left = `${rect.left - 10}px`;
        spotlight.style.width = `${rect.width + 20}px`;
        spotlight.style.height = `${rect.height + 20}px`;
    }

    positionTooltip(element, position) {
        const tooltip = document.querySelector('.tutorial-tooltip');
        const rect = element.getBoundingClientRect();

        // Position based on specified position
        switch(position) {
            case 'top':
                tooltip.style.top = `${rect.top - tooltip.offsetHeight - 20}px`;
                tooltip.style.left = `${rect.left + rect.width / 2 - tooltip.offsetWidth / 2}px`;
                break;
            case 'bottom':
                tooltip.style.top = `${rect.bottom + 20}px`;
                tooltip.style.left = `${rect.left + rect.width / 2 - tooltip.offsetWidth / 2}px`;
                break;
            case 'left':
                tooltip.style.top = `${rect.top + rect.height / 2 - tooltip.offsetHeight / 2}px`;
                tooltip.style.left = `${rect.left - tooltip.offsetWidth - 20}px`;
                break;
            case 'right':
                tooltip.style.top = `${rect.top + rect.height / 2 - tooltip.offsetHeight / 2}px`;
                tooltip.style.left = `${rect.right + 20}px`;
                break;
        }
    }

    getCurrentTutorial() {
        // This should track the current active tutorial
        // For now, return the first tutorial
        return this.tutorials.dashboard;
    }

    nextStep() {
        const tutorial = this.getCurrentTutorial();
        this.currentStep++;

        if (this.currentStep >= tutorial.steps.length) {
            this.completeTutorial();
        } else {
            this.showStep(tutorial.steps[this.currentStep]);
        }
    }

    previousStep() {
        if (this.currentStep > 0) {
            this.currentStep--;
            this.showStep(this.getCurrentTutorial().steps[this.currentStep]);
        }
    }

    async completeTutorial() {
        try {
            await fetch('/api/onboarding/complete-tutorial', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content
                }
            });
        } catch (error) {
            console.error('Error marking tutorial as complete:', error);
        }

        this.endTutorial();
    }

    skipTutorial() {
        if (confirm('Are you sure you want to skip this tutorial? You can always restart it later from the help menu.')) {
            this.endTutorial();
        }
    }

    endTutorial() {
        this.isActive = false;
        this.currentStep = 0;
        this.removeTutorialOverlay();
    }

    removeTutorialOverlay() {
        const overlay = document.querySelector('.tutorial-overlay');
        if (overlay) {
            overlay.remove();
        }
    }
}

// Tutorial Styles
const tutorialStyles = document.createElement('style');
tutorialStyles.textContent = `
    .tutorial-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        z-index: 10000;
        pointer-events: none;
    }

    .tutorial-backdrop {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.7);
        pointer-events: auto;
    }

    .tutorial-spotlight {
        position: absolute;
        background: transparent;
        border: 2px solid #3498db;
        border-radius: 8px;
        box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.7);
        z-index: 10001;
        transition: all 0.3s ease;
        pointer-events: none;
    }

    .tutorial-tooltip {
        position: absolute;
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        max-width: 400px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        z-index: 10002;
        pointer-events: auto;
    }

    .tutorial-tooltip-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
    }

    .tutorial-tooltip-header h3 {
        margin: 0;
        font-size: 1.25rem;
        color: #1f2937;
    }

    .tutorial-close-btn {
        background: none;
        border: none;
        font-size: 1.25rem;
        color: #9ca3af;
        cursor: pointer;
        padding: 0.25rem;
        transition: color 0.2s;
    }

    .tutorial-close-btn:hover {
        color: #374151;
    }

    .tutorial-tooltip-content {
        margin-bottom: 1rem;
    }

    .tutorial-tooltip-content p {
        margin: 0;
        color: #6b7280;
        line-height: 1.6;
    }

    .tutorial-tooltip-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
    }

    .tutorial-nav-buttons {
        display: flex;
        gap: 0.5rem;
    }

    .tutorial-btn {
        padding: 0.5rem 1rem;
        border-radius: 8px;
        border: none;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
    }

    .tutorial-btn-primary {
        background: linear-gradient(135deg, #006a4e, #3498db);
        color: white;
    }

    .tutorial-btn-primary:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 106, 78, 0.3);
    }

    .tutorial-btn-secondary {
        background: transparent;
        color: #6b7280;
        border: 1px solid #e5e7eb;
    }

    .tutorial-btn-secondary:hover {
        background: #f9fafb;
        color: #374151;
    }

    .tutorial-progress {
        margin-top: 1rem;
        padding-top: 1rem;
        border-top: 1px solid #e5e7eb;
        text-align: center;
        font-size: 0.875rem;
        color: #9ca3af;
    }
`;
document.head.appendChild(tutorialStyles);

// Initialize global tutorial manager
window.tutorialManager = new TutorialManager();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TutorialManager;
}
