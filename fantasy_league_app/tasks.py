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

def update_player_scores(app):
    """
    This is the ONLY scheduled task for live scores.
    It runs on a schedule, uses the 'get_in_play_stats' API, and performs
    a bulk update on the central Player table. It is fast and scalable.
    It also calculates rank changes to send push notifications.
    """
    with app.app_context():
        print(f"--- Running centralized player score update at {datetime.now()} ---")

        tours = ['pga', 'euro', 'kft', 'alt']
        data_golf_client = DataGolfClient()
        updated_tours = []

        for tour in tours:
            try:
                in_play_stats, error = data_golf_client.get_in_play_stats(tour)

                if error or not in_play_stats or not isinstance(in_play_stats, list):
                    continue

                player_scores_from_api = {player['dg_id']: player for player in in_play_stats}
                player_dg_ids = list(player_scores_from_api.keys())

                # --- START: New Notification Logic ---

                # 1. Find all active leagues for this tour
                active_leagues_on_tour = League.query.filter(
                    League.tour == tour,
                    League.is_finalized == False,
                    League.start_date <= datetime.utcnow()
                ).all()

                # 2. Calculate and store the OLD ranks for each league
                old_ranks_by_league = {}
                for league in active_leagues_on_tour:
                    entries = league.entries
                    # Calculate total scores based on current DB data
                    for entry in entries:
                        s1 = entry.player1.current_score if entry.player1 and entry.player1.current_score is not None else 0
                        s2 = entry.player2.current_score if entry.player2 and entry.player2.current_score is not None else 0
                        s3 = entry.player3.current_score if entry.player3 and entry.player3.current_score is not None else 0
                        entry.temp_score = s1 + s2 + s3

                    entries.sort(key=lambda x: x.temp_score)
                    old_ranks_by_league[league.id] = {entry.user_id: rank + 1 for rank, entry in enumerate(entries)}

                # --- END: Old Rank Calculation ---

                # 3. Update the Player scores in the database (your existing logic)
                players_in_db = Player.query.filter(Player.dg_id.in_(player_dg_ids)).all()
                players_to_update = []
                for player in players_in_db:
                    score_data = player_scores_from_api.get(player.dg_id)
                    new_score = score_data.get('current_score')
                    if score_data and new_score is not None:
                        players_to_update.append({
                            'id': player.id,
                            'current_score': new_score,
                            'thru': score_data.get('thru')
                        })

                if not players_to_update:
                    continue # Skip if there are no score changes

                db.session.bulk_update_mappings(Player, players_to_update)
                db.session.commit()
                print(f"Successfully updated {len(players_to_update)} players for tour: '{tour}'")
                if tour not in updated_tours:
                    updated_tours.append(tour)

                # --- START: New Rank Comparison and Notification ---

                # 4. Recalculate ranks with NEW scores and send notifications
                for league in active_leagues_on_tour:
                    entries = league.entries # Re-fetch or use existing entry objects
                    old_ranks = old_ranks_by_league.get(league.id, {})

                    # Recalculate total scores with the new data
                    for entry in entries:
                        s1 = entry.player1.current_score if entry.player1 and entry.player1.current_score is not None else 0
                        s2 = entry.player2.current_score if entry.player2 and entry.player2.current_score is not None else 0
                        s3 = entry.player3.current_score if entry.player3 and entry.player3.current_score is not None else 0
                        entry.temp_score = s1 + s2 + s3

                    entries.sort(key=lambda x: x.temp_score)

                    for new_rank_idx, entry in enumerate(entries):
                        new_rank = new_rank_idx + 1
                        old_rank = old_ranks.get(entry.user_id)

                        if old_rank is not None:
                            # NOTIFICATION 5: Big Jumps
                            if (old_rank - new_rank) >= 5: # Moved UP
                                send_push_notification(entry.user_id, "Big Mover! 🔥", f"You've jumped up to P{new_rank} in '{league.name}'!")
                            if (new_rank - old_rank) >= 5: # Moved DOWN
                                send_push_notification(entry.user_id, "Uh Oh... 😬", f"You've dropped to P{new_rank} in '{league.name}'.")

                            # NOTIFICATION 6: First Place Changes
                            if new_rank == 1 and old_rank != 1:
                                send_push_notification(entry.user_id, "You're in the Lead! 🥇", f"You've moved into 1st place in '{league.name}'!")
                            if old_rank == 1 and new_rank != 1:
                                send_push_notification(entry.user_id, "Leader Change!", f"You've been knocked out of 1st place in '{league.name}'.")

                # --- END: Notification Logic ---

            except Exception as e:
                print(f"An unexpected error occurred during score update for tour '{tour}': {e}")
                import traceback
                traceback.print_exc()
                db.session.rollback()

        if updated_tours:
            socketio.emit('scores_updated', {'updated_tours': updated_tours})
            print(f"Broadcast 'scores_updated' event for tours: {updated_tours}")

def schedule_score_updates_for_the_week(app):
    """
    JOB 1 - The Daily Scheduler.
    Runs every day at 5 AM from Thu-Sun. It finds the current day's tee times
    and schedules the updater job (update_player_scores) to run for that day.
    """
    with app.app_context():
        print(f"--- Running DAILY scheduler setup at {datetime.now()} ---")
        tours = ['pga', 'euro', 'kft', 'alt']
        data_golf_client = DataGolfClient()

        for tour in tours:
            print(f"Checking for tournament on tour: '{tour}'...")

            field_data, error = data_golf_client.get_tournament_field_updates(tour)

            if error or not field_data or not field_data.get('field'):
                print(f"No field data for tour '{tour}'. Skipping.")
                continue

            current_round = field_data.get("current_round")
            if not current_round:
                print(f"No current round data for tour '{tour}'. Skipping.")
                continue

            # --- Find Earliest & Latest Tee Times for the CURRENT Round ---
            tee_time_key = f"r{current_round}_teetime"
            earliest_tee_time = None
            latest_tee_time = None

            for player in field_data['field']:
                tee_time_str = player.get(tee_time_key)
                if tee_time_str:
                    tee_time = datetime.strptime(tee_time_str, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
                    if earliest_tee_time is None or tee_time < earliest_tee_time:
                        earliest_tee_time = tee_time
                    if latest_tee_time is None or tee_time > latest_tee_time:
                        latest_tee_time = tee_time

            if earliest_tee_time and latest_tee_time:
                # --- Calculate the precise window for today's updates ---
                start_updates_at = earliest_tee_time + timedelta(minutes=20)
                end_updates_at = latest_tee_time + timedelta(hours=5)

                # Create a unique ID for each day's job
                job_id = f"live_updater_{tour}_{datetime.now().strftime('%Y-%m-%d')}"

                # Use 'add_job' with 'replace_existing=True' to handle rescheduling
                scheduler.add_job(
                    id=job_id,
                    func=update_player_scores,
                    args=[app],
                    trigger='interval',
                    minutes=1,
                    start_date=start_updates_at,
                    end_date=end_updates_at,
                    replace_existing=True
                )
                print(f"SUCCESS: Scheduled/Rescheduled job '{job_id}' for tour '{tour}'.")
                print(f"  > Updates will run from {start_updates_at} to {end_updates_at}")
            else:
                print(f"Could not determine tee times for tour '{tour}' for round {current_round}. No job scheduled.")


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
            # After resetting, find all users and send them a notification
            all_users = User.query.filter_by(is_active=True).all()
            for user in all_users:
                send_push_notification(
                    user.id,
                    "New Week, New Leagues!",
                    "Player data has been updated. Check out the new leagues for this week's tournaments."
                )

        except Exception as e:
            print(f"ERROR: Could not reset player scores: {e}")
            db.session.rollback()

def send_deadline_reminders(app):
    """
    Runs periodically to send reminders for leagues whose entry deadline is approaching.
    """
    with app.app_context():
        with app.app_context():
            now = datetime.utcnow()

            # Check for 48h, 24h, and 6h windows
            windows = [48, 24, 6]
            for hours in windows:
                reminder_time = now + timedelta(hours=hours)

                # Find leagues whose deadline is in the next hour
                leagues_needing_reminder = League.query.filter(
                    League.entry_deadline.between(reminder_time, reminder_time + timedelta(hours=1)),
                    # You might need a more advanced way to track sent reminders per user/window
                ).all()

                for league in leagues_needing_reminder:
                    # Find users who have entered but not yet selected 3 players
                    entries_to_remind = LeagueEntry.query.filter(
                        LeagueEntry.league_id == league.id,
                        LeagueEntry.player3_id == None
                    ).all()

                    for entry in entries_to_remind:
                        send_push_notification(
                            entry.user_id,
                            f"Reminder for {league.name}",
                            f"Your entry is incomplete! The deadline is in {hours} hours."
                        )


#redundant
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
    Scheduled task to create new player buckets for upcoming tournaments.
    It fetches the tournament field and the latest betting odds,
    applies a cap to the odds, and populates the bucket.
    """
    with app.app_context():
        print("--- Running scheduled job: update_player_buckets ---")
        tours = ['pga', 'euro', 'kft', 'alt']
        data_golf_client = DataGolfClient()

        for tour in tours:
            print(f"--- Processing tour: {tour} ---")

            # --- Step 1: Fetch Tournament Field and Betting Odds ---
            field_data, field_error = data_golf_client.get_tournament_field_updates(tour)
            odds_data, odds_error = data_golf_client.get_betting_odds(tour) # Assuming this function exists

            if field_error or odds_error:
                current_app.logger.error(f"Failed to fetch data for {tour}. Field Error: {field_error}, Odds Error: {odds_error}")
                continue

            if not field_data or not field_data.get('field') or not odds_data:
                print(f"No complete field or odds data found for tour: {tour}. Skipping bucket update.")
                continue

            # --- Step 2: Create an efficient lookup map for odds ---
            # We assume odds_data is a list of dicts, each with 'dg_id' and 'odds_bet365'
            odds_map = {player['dg_id']: player.get('odds_bet365') for player in odds_data}

            # --- Step 3: Get or Create the Player Bucket ---
            bucket_name = f"{tour.upper()} Players - {field_data.get('event_name', datetime.utcnow().strftime('%Y-%m-%d'))}"
            latest_bucket = PlayerBucket.query.filter_by(name=bucket_name).first()

            if not latest_bucket:
                latest_bucket = PlayerBucket(name=bucket_name, tour=tour)
                db.session.add(latest_bucket)
                print(f"Created new player bucket: {latest_bucket.name}")
            else:
                print(f"Bucket '{bucket_name}' already exists. Updating players.")
                latest_bucket.players = [] # Clear out old players to ensure an accurate field

            # --- Step 4: Process Players and Apply Odds Cap ---
            for player_data in field_data['field']:
                player_dg_id = player_data.get('dg_id')
                if not player_dg_id:
                    continue

                player = Player.query.filter_by(dg_id=player_dg_id).first()
                if not player:
                    player = Player(dg_id=player_dg_id)
                    db.session.add(player)

                # Update player name details
                player_name_parts = player_data.get('player_name', ',').split(',')
                player.surname = player_name_parts[0].strip()
                player.name = player_name_parts[1].strip() if len(player_name_parts) > 1 else ''

                # --- Odds Capping Logic ---
                odds_from_api = odds_map.get(player_dg_id)

                if odds_from_api and isinstance(odds_from_api, (int, float)):
                    # If the odds are over 85, cap them at 85.
                    if odds_from_api > 85:
                        player.odds = 85
                    else:
                        player.odds = odds_from_api
                else:
                    # Set a high default for players without odds so they can still be picked
                    player.odds = 100

                latest_bucket.players.append(player)

        db.session.commit()
        print("--- Player bucket update finished successfully. ---")


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

            for winner in winners:
                send_push_notification(
                    winner.id,
                    f"You Won '{league.name}'!",
                    f"Congratulations! You finished in the top spot. Your winnings are on the way."
                )

            # --- Payout Logic ---
            club_admin = User.query.get(league.club_id) if not league.is_public else None
            total_prize, error = process_payouts(league, winners, club_admin)

            if error:
                print(f"Stripe payout failed for league {league.id}: {error}")
                continue


            # NOTIFICATION 4: Send "Payment Sent" message
            for winner in winners:
                send_push_notification(
                    winner.id,
                    "Payment Sent!",
                    f"Your winnings for the '{league.name}' league have been sent to your connected account."
                )
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

