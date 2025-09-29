/**
 * api.js - API Service
 * A central place for all fetch requests to the backend.
 */

// --- Fetch function for joining a league ---
export async function joinLeague(leagueCode, csrfToken) {
    try {
        const response = await fetch('/league/join', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ league_code: leagueCode }),
        });
        const data = await response.json();
        return response.ok ? { success: true, ...data } : { success: false, ...data };
    } catch (error) {
        console.error('API Error:', error);
        return { success: false, error: 'Could not connect to the server.' };
    }
}

// --- Fetch function for loading a league view ---
export async function fetchLeagueData(leagueId) {
    try {
        console.log('Fetching league....')
        const response = await fetch(`/league/${leagueId}`);
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        console.log(data)
        return { success: true, data: data };
    } catch (error) {
        console.error('API Error:', error);
        return { success: false, error: error.message };
    }
}