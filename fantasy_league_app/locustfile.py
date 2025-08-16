import os
import sys
from locust import HttpUser, task, between
from datetime import datetime, timedelta
import random

# --- Add project directory to Python's path ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Test Data ---
# Note: Ensure these users exist in your database before running the test.
REGULAR_USER_CREDS = {"email": "testuser@example.com", "password": "password"}
CLUB_ADMIN_CREDS = {"email": "clubadmin@example.com", "password": "password"}
SITE_ADMIN_CREDS = {"username": "GolfAdmin", "password": "4bover2A!"}

# --- Helper Functions ---
def get_csrf_token(client, url):
    """Fetches a CSRF token from a given page."""
    try:
        response = client.get(url, catch_response=True)
        if response.status_code == 200 and 'csrf_token' in response.text:
            token = response.text.split('name="csrf_token" value="')[1].split('"')[0]
            response.success()
            return token
        response.failure(f"Could not find CSRF token on {url}")
        return None
    except Exception as e:
        print(f"Exception getting CSRF token: {e}")
        return None



class RegularUser(HttpUser):
    wait_time = between(2, 5)
    league_id = 27

    def on_start(self):
        """Login as a regular user."""
        self.client.post("/auth/login", data=REGULAR_USER_CREDS)


    @task(5)
    def view_pages(self):
        """Simulates normal browsing behavior."""
        self.client.get("/leagues/browse")
        self.client.get("/player/all")
        self.client.get(f"/league/{self.league_id}")

    @task(2)
    def join_and_edit_league_entry(self):
        """Simulates the full user flow of joining and editing a league entry."""
        # --- Join a League ---
        add_entry_url = f"/league/add_entry/{self.league_id}"
        csrf_token = get_csrf_token(self.client, add_entry_url)
        if not csrf_token:
            return

        # Submit a valid entry
        entry_data = {
            "csrf_token": csrf_token,
            "player1": "290",
            "player2": "242",
            "player3": "298",
            "tie_breaker_answer": random.randint(1, 20)
        }
        with self.client.post(add_entry_url, data=entry_data, catch_response=True, name="/league/add_entry/[id]") as response:
            if "entry has been successfully submitted" in response.text:
                response.success()
                # Try to find the new entry ID for the edit task (simplified)
                # In a real scenario, you might need a more robust way to get this ID.
                self.entry_id = random.randint(1, 100)
            else:
                response.failure("Failed to join league.")
                return # Stop if joining failed

        if not self.entry_id:
            return

        # --- Edit the Entry ---
        edit_entry_url = f"/league/edit_entry/{self.entry_id}"
        csrf_token = get_csrf_token(self.client, edit_entry_url)
        if not csrf_token:
            return

        # Submit an edited entry
        edit_data = {
            "csrf_token": csrf_token,
            "player1": "283",
            "player2": "273",
            "player3": "241",
            "tie_breaker_answer": random.randint(1, 20)
        }
        self.client.post(edit_entry_url, data=edit_data, name="/league/edit_entry/[id]")

    @task(1)
    def chaos_test_access_control(self):
        """Attempts to access admin-only pages."""
        self.client.get("/admin/dashboard", name="/admin/* (forbidden)")

    @task(5)
    def view_leagues_and_players(self):
        """Simulates normal browsing behavior."""
        self.client.get("/leagues/browse")
        self.client.get("/player/all")

    @task(1)
    def chaos_test_access_control(self):
        """Attempts to access admin-only pages."""
        print("CHAOS TEST: Regular user trying to access admin dashboard.")
        self.client.get("/admin/dashboard", name="/admin/* (forbidden)")
        self.client.get("/admin/manage_leagues", name="/admin/* (forbidden)")

class ClubAdminUser(HttpUser):
    wait_time = between(2, 5)

    def on_start(self):
        """Login as a club admin."""
        self.client.post("/auth/login", data=CLUB_ADMIN_CREDS)

    @task(5)
    def view_dashboard(self):
        """Simulates normal club admin browsing."""
        self.client.get("/club-dashboard")

    @task(1)
    def chaos_test_invalid_league_creation(self):
        """Attempts to create leagues with invalid data."""
        print("CHAOS TEST: Club admin submitting invalid league forms.")

        # Get a valid CSRF token first
        csrf_token = get_csrf_token(self.client, "/league/create")
        if not csrf_token:
            return

        # --- Test Case 1: Empty form submission ---
        self.client.post("/league/create", {
            "csrf_token": csrf_token,
            "name": "", # Empty name
            "start_date": "",
            "player_bucket_id": "",
        }, name="/league/create (invalid)")

        # --- Test Case 2: Text where number is expected ---
        self.client.post("/league/create", {
            "csrf_token": csrf_token,
            "name": "Test League with Bad Data",
            "start_date": (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d'),
            "player_bucket_id": "1",
            "entry_fee": "not-a-number", # Invalid entry fee
            "prize_amount": "100",
            "max_entries": "100",
            "odds_limit": "100",
            "tie_breaker_question": "Test"
        }, name="/league/create (invalid)")

        # --- Test Case 3: Date in the past ---
        self.client.post("/league/create", {
            "csrf_token": csrf_token,
            "name": "Test League with Past Date",
            "start_date": (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
            "player_bucket_id": "1",
            "entry_fee": "10.00",
            "prize_amount": "50",
            "max_entries": "50",
            "odds_limit": "150",
            "tie_breaker_question": "Test"
        }, name="/league/create (invalid)")

class SiteAdminUser(HttpUser):
    wait_time = between(5, 10)

    def on_start(self):
        """Login as a site admin."""
        self.client.post("/auth/login_site_admin", data=SITE_ADMIN_CREDS)

    @task
    def chaos_test_manual_finalization(self):
        """Simulates the site admin manually triggering the finalization task."""
        print("CHAOS TEST: Site admin triggering manual league finalization.")

        # Get CSRF token from the admin dashboard
        csrf_token = get_csrf_token(self.client, "/admin/dashboard")
        if not csrf_token:
            return

        # The form on the dashboard needs a CSRF token
        self.client.post("/admin/manual-finalize-leagues", {
            "csrf_token": csrf_token
        }, name="/admin/manual-finalize-leagues")

