// fantasy_league_app/static/js/tutorial.js
class TutorialManager {
    constructor() {
        this.currentStep = 1;
        this.totalSteps = 5;
        this.overlay = document.getElementById('tutorial-overlay');
    }

    async init() {
        // Check if user should see tutorial
        const status = await this.getOnboardingStatus();

        if (status.should_show_tutorial) {
            this.showTutorial();
        }
    }

    async getOnboardingStatus() {
        try {
            const response = await fetch('/api/onboarding/status');

            // Check if user is authenticated (response should be JSON)
            const contentType = response.headers.get("content-type");
            if (!contentType || !contentType.includes("application/json")) {
                console.log('User not authenticated, skipping tutorial');
                return { should_show_tutorial: false };
            }

            if (!response.ok) {
                return { should_show_tutorial: false };
            }

            return await response.json();
        } catch (error) {
            console.error('Error fetching onboarding status:', error);
            return { should_show_tutorial: false };
        }
    }

    showTutorial() {
        if (this.overlay) {
            this.overlay.classList.add('active');
            this.updateProgress();
            document.body.style.overflow = 'hidden';
        }
    }

    hideTutorial() {
        if (this.overlay) {
            this.overlay.classList.remove('active');
            document.body.style.overflow = '';
        }
    }

    nextStep() {
        if (this.currentStep < this.totalSteps) {
            // Hide current step
            document.getElementById(`tutorial-step-${this.currentStep}`).classList.remove('active');

            // Show next step
            this.currentStep++;
            document.getElementById(`tutorial-step-${this.currentStep}`).classList.add('active');

            // Update progress and navigation
            this.updateProgress();
            this.updateNavigation();
        }
    }

    previousStep() {
        if (this.currentStep > 1) {
            // Hide current step
            document.getElementById(`tutorial-step-${this.currentStep}`).classList.remove('active');

            // Show previous step
            this.currentStep--;
            document.getElementById(`tutorial-step-${this.currentStep}`).classList.add('active');

            // Update progress and navigation
            this.updateProgress();
            this.updateNavigation();
        }
    }

    updateProgress() {
        const progressBar = document.getElementById('tutorial-progress');
        const progressText = document.getElementById('tutorial-step-text');

        if (progressBar) {
            const percentage = (this.currentStep / this.totalSteps) * 100;
            progressBar.style.width = `${percentage}%`;
        }

        if (progressText) {
            progressText.textContent = `Step ${this.currentStep} of ${this.totalSteps}`;
        }
    }

    updateNavigation() {
        const backBtn = document.getElementById('tutorial-back');
        const nextBtn = document.getElementById('tutorial-next');
        const finishBtn = document.getElementById('tutorial-finish');

        // Show/hide back button
        if (backBtn) {
            backBtn.style.display = this.currentStep > 1 ? 'inline-flex' : 'none';
        }

        // Show next or finish button
        if (this.currentStep === this.totalSteps) {
            if (nextBtn) nextBtn.style.display = 'none';
            if (finishBtn) finishBtn.style.display = 'inline-flex';
        } else {
            if (nextBtn) nextBtn.style.display = 'inline-flex';
            if (finishBtn) finishBtn.style.display = 'none';
        }
    }

    async completeTutorial() {
        try {
            const response = await fetch('/api/onboarding/complete-tutorial', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content
                }
            });

            const data = await response.json();

            if (data.success) {
                this.hideTutorial();

                // Show success message
                if (typeof window.showToast === 'function') {
                    window.showToast('Welcome to Fantasy Fairways! 🏌️', 'success');
                }
            }
        } catch (error) {
            console.error('Error completing tutorial:', error);
        }
    }

    skipTutorial() {
        const confirmed = confirm('Are you sure you want to skip the tutorial? You can always access it later from settings.');

        if (confirmed) {
            this.completeTutorial();
        }
    }
}

// Global functions for onclick handlers
window.tutorialManager = new TutorialManager();

window.nextTutorialStep = () => window.tutorialManager.nextStep();
window.previousTutorialStep = () => window.tutorialManager.previousStep();
window.completeTutorial = () => window.tutorialManager.completeTutorial();
window.skipTutorial = () => window.tutorialManager.skipTutorial();

// Helper functions for CTA buttons
window.showBeginnerLeagues = () => {
    window.tutorialManager.completeTutorial();
    // Navigate to browse leagues with beginner filter
    window.location.href = '/browse-leagues?filter=beginner';
};

window.showJoinModal = () => {
    window.tutorialManager.completeTutorial();
    // Trigger the join league modal
    const joinOverlay = document.getElementById('join-league-overlay');
    if (joinOverlay) {
        joinOverlay.classList.remove('hidden');
        joinOverlay.classList.add('active');
    }
};

// Initialize tutorial on page load
document.addEventListener('DOMContentLoaded', () => {
    window.tutorialManager.init();
});

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TutorialManager;
}

// Keyboard navigation support
document.addEventListener('keydown', (e) => {
    if (!window.tutorialManager.overlay?.classList.contains('active')) {
        return;
    }

    switch(e.key) {
        case 'ArrowRight':
        case 'Enter':
            e.preventDefault();
            window.tutorialManager.nextStep();
            break;
        case 'ArrowLeft':
            e.preventDefault();
            window.tutorialManager.previousStep();
            break;
        case 'Escape':
            e.preventDefault();
            window.tutorialManager.skipTutorial();
            break;
    }
});