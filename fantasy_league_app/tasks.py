from datetime import datetime, timedelta
from collections import defaultdict
import requests
import os
from sqlalchemy import func

from . import db, mail, socketio, scheduler # Make sure mail is imported if you use it in other tasks
from flask_mail import Message
from flask import current_app

from .data_golf_client import DataGolfClient

from collections import defaultdict # Add this import
from .models import League, Player, PlayerBucket, LeagueEntry, PlayerScore, User

from .stripe_client import process_payouts,  create_payout
from .utils import send_winner_notification_email

# def update_active_league_scores(app):
#     """
#     This function is the scheduled job. It finds all leagues that are currently
#     active, groups them by tour, and efficiently updates scores and ranks.
#     """
#     with app.app_context():
#         current_app.logger.info(f"--- Running scheduled score update at {datetime.now()} ---")

#         now = datetime.utcnow()
#         active_leagues = League.query.filter(League.start_date <= now, League.end_date >= now, League.is_finalized == False).all()

#         if not active_leagues:
#             current_app.logger.info("No active leagues found. Skipping score update.")
#             return

#         # Group active leagues by tour to minimize API calls
#         leagues_by_tour = defaultdict(list)
#         for league in active_leagues:
#             leagues_by_tour[league.tour].append(league)

#         current_app.logger.info(f"Found active leagues for tours: {list(leagues_by_tour.keys())}")

#         client = DataGolfClient()
#         for tour, leagues in leagues_by_tour.items():
#             current_app.logger.info(f"Fetching scores for tour: {tour}")
#             live_stats, error = client.get_live_tournament_stats(tour)

#             if error:
#                 current_app.logger.error(f"API Error for tour '{tour}': {error}")
#                 continue

#             # --- EFFICIENT SCORE UPDATE ---
#             # Create a map of dg_id to the new score for quick lookups
#             score_map = {player.get('dg_id'): player.get('total', 0) for player in live_stats if player.get('dg_id')}

#             # Get all unique player IDs that need updating for this tour
#             player_ids_to_update = score_map.keys()

#             # Fetch all relevant players from the database in one query
#             players_in_db = Player.query.filter(Player.dg_id.in_(player_ids_to_update)).all()

#             updated_count = 0
#             for player in players_in_db:
#                 new_score = score_map.get(player.dg_id)
#                 if new_score is not None and player.current_score != new_score:
#                     player.current_score = new_score
#                     updated_count += 1

#             if updated_count > 0:
#                 db.session.commit()
#                 current_app.logger.info(f"Successfully updated scores for {updated_count} players on tour '{tour}'.")
#             else:
#                 current_app.logger.info(f"No score changes for players on tour '{tour}'.")
#             # --- END OF EFFICIENT SCORE UPDATE ---

#             # --- RANK CALCULATION (Now runs after scores are updated) ---
#             for league in leagues:
#                 current_app.logger.info(f"Calculating ranks for league: {league.name} (ID: {league.id})")

#                 entries = league.entries
#                 if not entries:
#                     continue

#                 scored_entries = []
#                 for entry in entries:
#                     p1_score = entry.player1.current_score if entry.player1 and entry.player1.current_score is not None else 0
#                     p2_score = entry.player2.current_score if entry.player2 and entry.player2.current_score is not None else 0
#                     p3_score = entry.player3.current_score if entry.player3 and entry.player3.current_score is not None else 0
#                     total_score = p1_score + p2_score + p3_score
#                     scored_entries.append({'entry': entry, 'score': total_score})

#                 sorted_entries = sorted(scored_entries, key=lambda x: x['score'])

#                 last_score = -9999
#                 last_rank = 0
#                 for i, item in enumerate(sorted_entries):
#                     rank = i + 1 if item['score'] > last_score else last_rank
#                     item['entry'].current_rank = rank
#                     last_score = item['score']
#                     last_rank = rank

#                 db.session.commit()
#                 current_app.logger.info(f"Successfully updated ranks for {len(entries)} entries in {league.name}.")

#                 # Emit update to clients
#                 socketio.emit('scores_updated', {'league_id': league.id}, room=f'league_{league.id}')

#         current_app.logger.info("--- Weekly bucket update finished. ---")

# def update_active_league_scores(app):
#     """
#     This function is the scheduled job. It finds all leagues that are currently
#     active, groups them by tour, and efficiently updates scores and ranks.
#     """
#     print("--- Task triggered. Attempting to enter app context... ---")

#     try:
#         with app.app_context():
#             print("--- App context entered successfully. Starting update logic. ---")

#             now = datetime.utcnow()
#             print(f"--- Current UTC time: {now} ---")

#             print("--- Querying for active leagues... ---")
#             active_leagues = League.query.filter(
#                 League.start_date <= now,
#                 League.end_date >= now,
#                 League.is_finalized == False
#             ).all()
#             print(f"--- Found {len(active_leagues)} active leagues. ---")

#             if not active_leagues:
#                 print("--- No active leagues found. Task finished. ---")
#                 return

#             # Group active leagues by tour to minimize API calls
#             leagues_by_tour = defaultdict(list)
#             for league in active_leagues:
#                 leagues_by_tour[league.tour].append(league)
#             print(f"--- Leagues grouped by tour: {dict(leagues_by_tour)} ---")

#             data_golf_client = DataGolfClient()

#             for tour, leagues in leagues_by_tour.items():
#                 print(f"--- Updating scores for tour: {tour} ---")

#                 live_scores_data, error = data_golf_client.get_live_tournament_stats(tour)
#                 if error or not live_scores_data:
#                     print(f"--- No live data or error for tour {tour}. Error: {error}. Skipping. ---")
#                     continue

#                 print(f"--- Fetched {len(live_scores_data)} player scores from API for tour {tour}. ---")

#                 player_scores = {player['dg_id']: player for player in live_scores_data}
#                 all_player_ids_in_tour = list(player_scores.keys())

#                 print(f"--- Updating {len(all_player_ids_in_tour)} players in the database... ---")
#                 players_to_update = Player.query.filter(Player.dg_id.in_(all_player_ids_in_tour)).all()

#                 for player in players_to_update:
#                     score_data = player_scores.get(player.dg_id)
#                     if score_data:
#                         player.current_score = score_data.get('total')
#                         player.thru = score_data.get('thru')

#                 db.session.commit()
#                 print("--- Database commit successful. ---")

#                 # --- Update League Ranks and Notify Frontend ---
#                 for league in leagues:
#                     # ... (The rest of the logic remains the same) ...
#                     entries = LeagueEntry.query.filter_by(league_id=league.id).all()
#                     # ...
#                     db.session.commit()
#                     socketio.emit('scores_updated', {'league_id': league.id}, room=f'league_{league.id}')

#             print("--- Score update process finished successfully. ---")

#     except Exception as e:
#         # This will catch any unexpected error and print it to your terminal
#         print(f"!!! AN UNEXPECTED ERROR OCCURRED: {e} !!!")
#         import traceback
#         traceback.print_exc()


def update_player_scores(app):
    """
    This is the ONLY scheduled task for live scores.
    It runs on a schedule, fetches data for all active tours, and performs
    a bulk update on the central Player table. It is fast and scalable.
    """
    with app.app_context():
        print(f"--- Running centralized player score update at {datetime.now()} ---")

        tours = ['pga', 'euro', 'kft', 'alt']
        data_golf_client = DataGolfClient()
        updated_tours = []

        for tour in tours:
            try:
               # this method returns the list of players directly
                live_scores, error = data_golf_client.get_in_play_stats(tour)

                if error:
                    print(f"API Error for tour '{tour}': {error}")
                    continue

                if not live_scores or not isinstance(live_scores, list):
                    print(f"No valid player data found for tour: '{tour}'.")
                    continue

                # --- 1. Create a quick lookup dictionary for API scores ---
                player_scores_from_api = {player['dg_id']: player for player in live_scores}
                player_dg_ids = list(player_scores_from_api.keys())

                # --- 2. Fetch the corresponding players from OUR database ---
                # This gets us the all-important primary key (player.id)
                players_in_db = Player.query.filter(Player.dg_id.in_(player_dg_ids)).all()

                # --- 3. Prepare the data for the bulk update ---
                players_to_update = []
                for player in players_in_db:
                    score_data = player_scores_from_api.get(player.dg_id)
                    new_score = score_data.get('current_score')

                    if score_data and new_score is not None:
                        players_to_update.append({
                            'id': player.id,  # CRITICAL: Provide the primary key
                            'current_score': new_score,
                            'thru': score_data.get('thru'),
                            'today': score_data.get('today')
                        })

                # --- 4. Perform the efficient bulk update ---
                if players_to_update:
                    db.session.bulk_update_mappings(Player, players_to_update)
                    db.session.commit()
                    print(f"Successfully updated {len(players_to_update)} players for tour: '{tour}'")
                    if tour not in updated_tours:
                        updated_tours.append(tour)

            except Exception as e:
                print(f"An unexpected error occurred during score update for tour '{tour}': {e}")
                import traceback
                traceback.print_exc()
                db.session.rollback()

        if updated_tours:
            socketio.emit('scores_updated', {'updated_tours': updated_tours})
            print(f"Broadcast 'scores_updated' event for tours: {updated_tours}")


# def update_all_player_scores():
#     """
#     This is the ONLY scheduled task for live scores.
#     It runs every minute, fetches data for all active tours, and updates
#     the central Player table. It is completely independent of leagues.
#     """
#     with scheduler.app.app_context():
#         print(f"--- Running centralized player score update at {datetime.now()} ---")
#         tours = ['pga', 'euro', 'kft', 'alt']
#         api_key = os.environ.get("DATA_GOLF_API_KEY")
#         updated_tours = []

#         for tour in tours:
#             try:
#                 url = f"https://feeds.datagolf.com/real-time/leaderboard?tour={tour}&key={api_key}"
#                 response = requests.get(url)
#                 response.raise_for_status()
#                 data = response.json()

#                 if data and data.get('leaderboard'):
#                     players_to_update = []
#                     for player_score in data['leaderboard']:
#                         players_to_update.append({
#                             'dg_id': player_score.get('player_id'),
#                             'current_score': player_score.get('total_to_par'),
#                             'thru': player_score.get('thru')
#                         })

#                     # Perform a bulk update for efficiency
#                     if players_to_update:
#                         db.session.bulk_update_mappings(Player, players_to_update)
#                         db.session.commit()
#                         print(f"Successfully updated {len(players_to_update)} players for tour: '{tour}'")
#                         if tour not in updated_tours:
#                             updated_tours.append(tour)
#                 else:
#                     print(f"No active tournament found for tour: '{tour}'.")

#             except Exception as e:
#                 print(f"An error occurred during score update for tour '{tour}': {e}")
#                 db.session.rollback()

#         # After updating all tours, send a single broadcast
#         if updated_tours:
#             socketio.emit('scores_updated', {'updated_tours': updated_tours})
#             print(f"Broadcast 'scores_updated' event for tours: {updated_tours}")

# def schedule_score_updates_for_the_week():
#     """
#     JOB 1 - The Scheduler:
#     Runs at 5 AM on Thursday. It loops through each tour, finds the earliest
#     tee time for each, and schedules a DEDICATED update job for each active tour.
#     """
#     with current_app.app_context():
#         print("--- Running weekly task to schedule score updates for each tour ---")
#         tours = ['pga', 'euro', 'kft', 'alt']
#         api_key = os.environ.get("DATA_GOLF_API_KEY")

#         for tour in tours:
#             earliest_tee_time_for_tour = None
#             url = f"https://feeds.datagolf.com/field-updates?tour={tour}&key={api_key}"

#             print(f"Checking for tournaments on tour: '{tour}'...")

#             try:
#                 response = requests.get(url)
#                 response.raise_for_status()
#                 data = response.json()

#                 if not data.get('field') or not data.get('event_name'):
#                     print(f"No active tournament found for tour: '{tour}'. Skipping.")
#                     continue

#                 for player in data.get('field', []):
#                     tee_time_str = player.get('r1_teetime')
#                     if tee_time_str:
#                         tee_time = datetime.strptime(tee_time_str, '%Y-%m-%d %H:%M')
#                         if earliest_tee_time_for_tour is None or tee_time < earliest_tee_time_for_tour:
#                             earliest_tee_time_for_tour = tee_time

#             except requests.exceptions.RequestException as e:
#                 print(f"API Error for tour '{tour}': {e}")
#                 continue
#             except (ValueError, TypeError) as e:
#                 print(f"Data parsing error for tour '{tour}': {e}")
#                 continue

#             if earliest_tee_time_for_tour:
#                 start_time = earliest_tee_time_for_tour + timedelta(minutes=20)
#                 days_until_monday = (7 - start_time.weekday()) % 7
#                 end_time = (start_time + timedelta(days=days_until_monday)).replace(hour=3, minute=0, second=0)

#                 job_id = f"score_updater_{tour}_{start_time.strftime('%Y-%U')}"

#                 if scheduler.get_job(job_id):
#                     print(f"Job '{job_id}' already exists. Skipping.")
#                     continue

#                 scheduler.add_job(
#                     id=job_id,
#                     func=update_scores_for_tour,
#                     trigger='interval',
#                     minutes=5,
#                     start_date=start_time,
#                     end_date=end_time,
#                     args=[tour]
#                 )
#                 print(f"SUCCESS: Created job '{job_id}' for tour '{tour}'.")
#                 print(f"  > Start: {start_time}, End: {end_time}")
#             else:
#                 print(f"No tee times found for tour: '{tour}'. No job created.")

#         print("--- Weekly scheduling task finished ---")


def update_scores_for_tour(tour):
    """
    JOB 2 - The Updater:
    This function is the target of the scheduled jobs. It updates scores
    for the specific tour it is given.
    """
    with scheduler.app.app_context():
        print(f"Running score update for tour: '{tour}' at {datetime.now()}")
        api_key = os.environ.get("DATA_GOLF_API_KEY")
        url = f"https://feeds.datagolf.com/real-time/leaderboard?tour={tour}&key={api_key}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            if data and data.get('leaderboard'):
                for playerScore in data['leaderboard']:
                    player = Player.query.filter_by(dg_id=playerScore.get('player_id')).first()
                    if player:
                        player.current_score = playerScore.get('total_to_par')
                        player.thru = playerScore.get('thru')
                db.session.commit()
                print(f"Successfully updated scores for players on the '{tour}' tour.")
            else:
                print(f"No leaderboard data returned for tour: '{tour}'.")

        except Exception as e:
            print(f"An error occurred during score update for tour '{tour}': {e}")
            db.session.rollback()

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
        reminder_window_start = now + timedelta(hours=24)
        reminder_window_end = now + timedelta(hours=48)

         # Query against the actual 'start_date' database column.
        # adjust the window by -1 hour to match the logic of the entry_deadline property
        # (deadline is 3 hour before the tournament starts).
        leagues_nearing_deadline = League.query.filter(
            League.reminder_sent == False,
            League.start_date.between(
                reminder_window_start + timedelta(hours=3),
                reminder_window_end + timedelta(hours=3)
            )
        ).all()

        if not leagues_nearing_reminder:
            print(f"--- No deadline reminders to send at {datetime.now()} ---")
            return

        print(f"--- Found {len(leagues_needing_reminder)} league(s) needing reminders. ---")

        for league in leagues_nearing_reminder:
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


# In fantasy_league_app/tasks.py

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
                print(f"Processing tour: {tour}")

                # 1. Fetch the schedule for the current tour
                schedule_url = f"https://feeds.datagolf.com/get-schedule?tour={tour}&file_format=json&key={API_KEY}"
                response = requests.get(schedule_url)
                response.raise_for_status()
                schedule_data = response.json().get('schedule', [])

                # Find the first upcoming tournament in the next 7 days
                upcoming_tournament = None
                for tournament in schedule_data:
                    start_date = datetime.strptime(tournament.get('start_date'), '%Y-%m-%d').date()
                    if today <= start_date < today + timedelta(days=7):
                        upcoming_tournament = tournament
                        break # Found the first one, stop looking

                if not upcoming_tournament:
                    print(f"No upcoming tournaments found for tour '{tour}' in the next 7 days.")
                    continue # Move to the next tour

                event_name = upcoming_tournament.get('event_name')
                event_id = upcoming_tournament.get('event_id')

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
                    event_id=event_id,
                    tour=tour
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

            except requests.exceptions.RequestException as e:
                print(f"API Error for tour '{tour}': {e}")
            except Exception as e:
                print(f"An unexpected error occurred for tour '{tour}': {e}")
                db.session.rollback()

        # 5. Clean up old, unused buckets (moved outside the tour loop to run once at the end)
        print("\n--- Starting cleanup of old buckets ---")
        cleanup_date = datetime.utcnow() - timedelta(days=100)
        old_buckets = PlayerBucket.query.filter(PlayerBucket.created_at < cleanup_date).all()

        deleted_count = 0
        for bucket in old_buckets:
            is_in_use_by_active_league = any(not league.is_finalized for league in bucket.leagues)

            if not is_in_use_by_active_league:
                db.session.delete(bucket)
                deleted_count += 1

        if deleted_count > 0:
            db.session.commit()
            print(f"Cleaned up and deleted {deleted_count} old, unused player buckets.")
        else:
            print("No old buckets to clean up.")

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

