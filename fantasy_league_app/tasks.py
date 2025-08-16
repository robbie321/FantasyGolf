from datetime import datetime, timedelta
from collections import defaultdict
import requests
from sqlalchemy import func

from . import db, mail, socketio # Make sure mail is imported if you use it in other tasks
from flask_mail import Message

from .data_golf_client import DataGolfClient

from collections import defaultdict # Add this import
from .models import League, Player, PlayerBucket, LeagueEntry, PlayerScore, User

from .stripe_client import process_payouts,  create_payout
from .utils import send_winner_notification_email

def update_active_league_scores(app):
    """
    This function is the scheduled job. It finds all leagues that are currently
    active and updates the scores for players in those leagues.
    """
    with app.app_context():
        print(f"--- Running scheduled score update at {datetime.now()} ---")

        now = datetime.utcnow()
        active_leagues = League.query.filter(League.start_date <= now, League.end_date >= now).all()

        if not active_leagues:
            print("No active leagues found. Skipping API call.")
            return

        leagues_by_tour = defaultdict(list)
        for league in active_leagues:
            leagues_by_tour[league.tour].append(league)

        print(f"Found active leagues for tours: {list(leagues_by_tour.keys())}")

        client = DataGolfClient()
        for tour, leagues in leagues_by_tour.items():
            print(f"Fetching scores for tour: {tour}")
            live_stats, error = client.get_live_tournament_stats(tour)

            if error:
                print(f"An unexpected error occurred for tour '{tour}': {error}")
                continue  # Skip to the next tour

            updated_count = 0
            for api_player in live_stats:
                dg_id = api_player.get('dg_id')
                if not dg_id:
                    continue

                player_in_db = Player.query.filter_by(dg_id=dg_id).first()

                if player_in_db:
                    player_in_db.current_score = api_player.get('total', 0)

                    tee_time_data = api_player.get('tee_time', None)
                    if isinstance(tee_time_data, list) and tee_time_data:
                        player_in_db.tee_time = tee_time_data[0]
                    else:
                        player_in_db.tee_time = tee_time_data

                    updated_count += 1

            db.session.commit()
            print(f"Successfully updated scores for {updated_count} players on tour '{tour}'.")

            if updated_count > 0:
                for league in leagues:
                    print(f"Emitting scores_updated for league_id: {league.id}")
                    socketio.emit('scores_updated', {'league_id': league.id}, room=f'league_{league.id}')

# --- Task to reset all player scores weekly ---
def reset_player_scores(app):
    """
    Scheduled to run weekly to reset the 'current_score' for all players to 0.
    This prepares the database for the new week of tournaments.
    """
    with app.app_context():
        print(f"--- Running weekly player score reset at {datetime.now()} ---")
        try:
            # This is a bulk update, which is very efficient
            updated_rows = db.session.query(Player).update({"current_score": 0})
            db.session.commit()
            print(f"Successfully reset scores for {updated_rows} players.")
        except Exception as e:
            print(f"ERROR: Could not reset player scores: {e}")
            db.session.rollback()

def send_deadline_reminders(app):
    """
    Runs periodically to send reminders for leagues whose deadline is approaching.
    """
    with app.app_context():
        now = datetime.utcnow()
        # Find leagues whose entry deadline is in the next 24 hours and haven't had a reminder sent
        reminder_window_start = now
        reminder_window_end = now + timedelta(hours=24)

        leagues_needing_reminder = League.query.filter(
            League.entry_deadline.between(reminder_window_start, reminder_window_end),
            League.reminder_sent == False
        ).all()

        if not leagues_needing_reminder:
            print(f"--- No deadline reminders to send at {datetime.now()} ---")
            return

        print(f"--- Found {len(leagues_needing_reminder)} league(s) needing reminders. ---")

        for league in leagues_needing_reminder:
            recipients = [entry.user.email for entry in league.entries]

            if not recipients:
                # Mark as sent even if no one has joined to prevent re-checking
                league.reminder_sent = True
                continue

            msg = Message(f'Reminder: Entry Deadline for "{league.name}"',
                          sender=app.config['MAIL_DEFAULT_SENDER'],
                          bcc=recipients) # Use BCC to protect privacy
            msg.body = f"""Hi everyone,

This is a reminder that the deadline to submit or edit your entry for the league "{league.name}" is approaching.

Deadline: {league.entry_deadline.strftime('%A, %d %B %Y at %H:%M')} UTC.

Make sure your picks are in! Good luck.
"""
            mail.send(msg)

            # Mark the league so we don't send reminders again
            league.reminder_sent = True
            print(f"Sent reminder for league: {league.name}")

        db.session.commit()

def settle_finished_leagues(app):
    """
    This job runs periodically to perform a final score update for leagues
    that have just ended.
    """
    with app.app_context():
        now = datetime.utcnow()
        # Look for leagues that ended in the last 15 minutes and are not yet finalized
        recently_finished = now - timedelta(minutes=15)

        leagues_to_settle = League.query.filter(
            League.end_date.between(recently_finished, now),
            League.is_finalized == False
        ).all()

        if not leagues_to_settle:
            print(f"--- No leagues to settle at {datetime.now()} ---")
            return

        print(f"--- Found {len(leagues_to_settle)} league(s) to settle. Performing final score update. ---")

        API_KEY = app.config['DATA_GOLF_API_KEY']
        # The pre-tournament endpoint also contains the final results after an event.
        url = f"https://feeds.datagolf.com/preds/pre-tournament?tour=pga&odds_format=decimal&key={API_KEY}"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # We create a dictionary of player scores for quick lookup
            player_scores = {}
            for api_player in data.get('field', []):
                player_name_parts = api_player.get('player_name', '').split(', ')
                if len(player_name_parts) == 2:
                    surname, name = player_name_parts[0].strip(), player_name_parts[1].strip()
                    # Create a unique key for the dictionary
                    player_key = f"{name.lower()} {surname.lower()}"
                    player_scores[player_key] = api_player.get('to_par', 0)

            if not player_scores:
                print("Could not fetch final player scores from API.")
                return

            # Get all players from our database
            all_db_players = Player.query.all()
            updated_count = 0
            for player in all_db_players:
                player_key = f"{player.name.lower()} {player.surname.lower()}"
                if player_key in player_scores:
                    player.current_score = player_scores[player_key]
                    updated_count += 1

            db.session.commit()
            print(f"Final scores updated for {updated_count} players.")

        except requests.exceptions.RequestException as e:
            print(f"Error fetching final scores from API: {e}")


def update_player_buckets(app):
    """
    Scheduled to run weekly. Fetches upcoming tournaments for major tours,
    creates player buckets for them, and cleans up old, unused buckets.
    """
    with app.app_context():
        print(f"--- Running weekly player bucket update at {datetime.now()} ---")

        API_KEY = app.config.get('DATA_GOLF_API_KEY')
        if not API_KEY:
            print("ERROR: Data Golf API key not configured. Aborting task.")
            return

        tours = ['pga', 'alt', 'euro', 'kft']
        today = datetime.utcnow().date()

        for tour in tours:
            try:
                # 1. Fetch the schedule for the current tour
                schedule_url = f"https://feeds.datagolf.com/get-schedule?tour={tour}&file_format=json&key={API_KEY}"
                response = requests.get(schedule_url)
                response.raise_for_status()
                schedule_data = response.json().get('schedule', [])

                # Find the tournament for the upcoming week
                for tournament in schedule_data:
                    start_date = datetime.strptime(tournament.get('start_date'), '%Y-%m-%d').date()
                    # Check if the tournament starts within the next 7 days
                    if today <= start_date < today + timedelta(days=7):
                        event_name = tournament.get('event_name')
                        event_id = tournament.get('event_id')

                        # 2. Check if a bucket for this event already exists
                        if PlayerBucket.query.filter_by(name=event_name).first():
                            print(f"Bucket '{event_name}' already exists. Skipping.")
                            continue

                        # 3. Fetch the player field for the new tournament
                        field_url = f"https://feeds.datagolf.com/field-updates?tour={tour}&event_id={event_id}&key={API_KEY}"
                        field_response = requests.get(field_url)
                        field_response.raise_for_status()
                        player_list = field_response.json().get('field', [])

                        if not player_list:
                            print(f"No player field found for '{event_name}'. Skipping bucket creation.")
                            continue

                        # 4. Create the new bucket and add players
                            new_bucket = PlayerBucket(
                                name=event_name,
                                description=f"Players for {event_name}",
                                event_id=event_id
                            )
                            db.session.add(new_bucket)

                        for api_player in player_list:
                            dg_id = api_player.get('dg_id')
                            if not dg_id: continue

                            player = Player.query.filter_by(dg_id=dg_id).first()
                            if not player:
                                # Create a new player if they don't exist in our DB
                                name_parts = api_player.get('player_name', '').split(' ')
                                name = name_parts[0]
                                surname = ' '.join(name_parts[1:])
                                player = Player(dg_id=dg_id, name=name, surname=surname)
                                db.session.add(player)

                            new_bucket.players.append(player)

                        db.session.commit()
                        print(f"Successfully created bucket '{event_name}' with {len(new_bucket.players)} players.")
                        break # Move to the next tour

            except requests.exceptions.RequestException as e:
                print(f"API Error for tour '{tour}': {e}")
            except Exception as e:
                print(f"An unexpected error occurred for tour '{tour}': {e}")
                db.session.rollback()

        # 5. Clean up old, unused buckets
        cleanup_date = datetime.utcnow() - timedelta(days=10)
        old_buckets = PlayerBucket.query.filter(PlayerBucket.created_at < cleanup_date).all()

        deleted_count = 0
        for bucket in old_buckets:
            # Only delete if no leagues are currently using this bucket
            # Check if any of the leagues using this bucket are NOT finalized.
            is_in_use_by_active_league = any(not league.is_finalized for league in bucket.leagues)

            # If no active leagues are using it, it's safe to delete.
            if not is_in_use_by_active_league:
                db.session.delete(bucket)
                deleted_count += 1
            # --- END OF FIX ---

        if deleted_count > 0:
            db.session.commit()
            print(f"Cleaned up and deleted {deleted_count} old, unused player buckets.")

        print("--- Weekly bucket update finished. ---")


# --- Automated Weekly Task to Finalize Leagues ---
def finalize_finished_leagues(app):
    """
    Finds finished leagues, fetches the tie-breaker score, determines winner(s),
    and processes payouts.
    """
    with app.app_context():
        print(f"--- Running weekly league finalization at {datetime.now()} ---")
        client = DataGolfClient()

        leagues_to_finalize = League.query.filter(
            League.end_date < datetime.utcnow(),
            League.is_finalized == False
        ).all()

        if not leagues_to_finalize:
            print("No leagues to finalize this week.")
            return

        for league in leagues_to_finalize:
            entries = league.entries
            if not entries:
                print(f"Skipping league '{league.name}' (ID: {league.id}) as it has no entries.")
                league.is_finalized = True
                db.session.commit()
                continue

            # --- Calculate Winner(s) ---
            for entry in entries:
                p1_score = entry.player1.current_score if entry.player1 else 0
                p2_score = entry.player2.current_score if entry.player2 else 0
                p3_score = entry.player3.current_score if entry.player3 else 0
                entry.total_score = p1_score + p2_score + p3_score

            min_score = min(entry.total_score for entry in entries)
            top_entries = [entry for entry in entries if entry.total_score == min_score]

            winners = []
            if len(top_entries) == 1:
                winners = [top_entries[0].user]
            else:
                actual_answer = league.tie_breaker_actual_answer
                if actual_answer is not None:
                    min_diff = min(abs(e.tie_breaker_answer - actual_answer) for e in top_entries)
                    winners = [e.user for e in top_entries if abs(e.tie_breaker_answer - actual_answer) == min_diff]
                else:
                    winners = [e.user for e in top_entries]

            league.winners = winners

            # --- Payout Logic ---
            club_admin = User.query.get(league.club_id) if not league.is_public else None
            total_prize, error = process_payouts(league, winners, club_admin)

            if error:
                print(f"Stripe payout failed for league {league.id}: {error}")
                continue

            # --- Archive Scores & Finalize ---
            all_players_in_league = set()
            for entry in entries:
                all_players_in_league.add(entry.player1)
                all_players_in_league.add(entry.player2)
                all_players_in_league.add(entry.player3)

            for player in all_players_in_league:
                if player:
                    historical_score = PlayerScore(
                        player_id=player.id,
                        league_id=league.id,
                        score=player.current_score
                    )
                    db.session.add(historical_score)

            league.is_finalized = True
            db.session.commit()
            send_winner_notification_email(league)
            print(f"Successfully finalized league '{league.name}' (ID: {league.id}). Winners: {[w.full_name for w in winners]}")

        print("--- Weekly league finalization finished. ---")