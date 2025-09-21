/**
 * main.js - The Main Entry Point
 * This file imports functionality from other modules and initializes
 * all the event listeners when the page loads.
 */
import { setupNavigation } from './navigation.js';
import { setupModalHandlers } from './ui.js';
import { setupViews } from './views.js';
import { setupLeaderboards } from './leaderboard.js';

document.addEventListener('DOMContentLoaded', function() {
    console.log("Initializing application...");

    // Set up the main single-page application navigation
    setupNavigation();

    // Set up listeners for UI components like the "Join League" modal
    setupModalHandlers();

    // Set up listeners for dynamically created content (like "View Leaderboard" buttons)
    setupViews();

    //load leaderboards
    setupLeaderboards();

    console.log("Application initialized.");
});