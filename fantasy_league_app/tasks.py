from datetime import datetime, timedelta, timezone
from collections import defaultdict
import requests
import os
from sqlalchemy import func

from . import db, mail, socketio, create_app  # Make sure mail is imported if you use it in other tasks
from flask_mail import Message
from flask import current_app

from .data_golf_client import DataGolfClient

from collections import defaultdict # Add this import
from .models import League, Player, PlayerBucket, LeagueEntry, PlayerScore, User, PushSubscription, db
from celery import shared_task
from .stripe_client import process_payouts,  create_payout
from .utils import send_winner_notification_email, send_push_notification, send_email

@shared_task(bind=True)
def update_player_scores(self, tour, end_time_iso):
    """
    Fetches live scores for a tour, updates the database, calculates rank changes,
    and reschedules itself to run again every 3 minutes until the end_time is reached.
    """
    app = create_app()
    with app.app_context():
        print(f"--- Running score update for tour '{tour}' at {datetime.now()} ---")

        # Convert the end_time string back to a timezone-aware datetime object
        end_time = datetime.fromisoformat(end_time_iso).replace(tzinfo=timezone.utc)

        try:
            data_golf_client = DataGolfClient()
            in_play_stats, error = data_golf_client.get_in_play_stats(tour)

            if not error and in_play_stats and isinstance(in_play_stats, list):
                player_scores_from_api = {player['dg_id']: player for player in in_play_stats}
                player_dg_ids = list(player_scores_from_api.keys())

                # --- START: Notification Logic ---
                active_leagues_on_tour = League.query.filter(
                    League.tour == tour,
                    League.is_finalized == False,
                    League.start_date <= datetime.utcnow()
                ).all()

                old_ranks_by_league = {}
                for league in active_leagues_on_tour:
                    entries = league.entries
                    for entry in entries:
                        s1 = entry.player1.current_score if entry.player1 and entry.player1.current_score is not None else 0
                        s2 = entry.player2.current_score if entry.player2 and entry.player2.current_score is not None else 0
                        s3 = entry.player3.current_score if entry.player3 and entry.player3.current_score is not None else 0
                        entry.temp_score = s1 + s2 + s3
                    entries.sort(key=lambda x: x.temp_score)
                    old_ranks_by_league[league.id] = {entry.user_id: rank + 1 for rank, entry in enumerate(entries)}

                # --- Update Player scores in the database ---
                players_in_db = Player.query.filter(Player.dg_id.in_(player_dg_ids)).all()
                players_to_update = []
                for player in players_in_db:
                    score_data = player_scores_from_api.get(player.dg_id)

                    if score_data:
                        new_score = score_data.get('current_score')
                        player_pos = score_data.get('current_pos', '').upper() # Get player position
                        if  new_score is not None and player_pos in ['WD', 'CUT', 'DF']:
                            new_score += 10 # Add 10-stroke penalty
                            print(f"Applying +10 penalty to {player.full_name} for status: {player_pos}")

                        if new_score is not None:
                            players_to_update.append({
                                'id': player.id,
                                'current_score': new_score,
                                'thru': score_data.get('thru'),
                                'current_pos': player_pos
                            })

                if players_to_update:
                    db.session.bulk_update_mappings(Player, players_to_update)
                    db.session.commit()
                    print(f"Successfully updated {len(players_to_update)} players for tour: '{tour}'")
                    socketio.emit('scores_updated', {'updated_tours': [tour]})

                    # --- Recalculate ranks and send notifications ---
                    for league in active_leagues_on_tour:
                        entries = league.entries
                        old_ranks = old_ranks_by_league.get(league.id, {})
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
                                if (old_rank - new_rank) >= 5:
                                    send_push_notification(entry.user_id, "Big Mover! 🔥", f"You've jumped up to P{new_rank} in '{league.name}'!")
                                if (new_rank - old_rank) >= 5:
                                    send_push_notification(entry.user_id, "Uh Oh... 😬", f"You've dropped to P{new_rank} in '{league.name}'.")
                                if new_rank == 1 and old_rank != 1:
                                    send_push_notification(entry.user_id, "You're in the Lead! 🥇", f"You've moved into 1st place in '{league.name}'!")
                                if old_rank == 1 and new_rank != 1:
                                    send_push_notification(entry.user_id, "Leader Change!", f"You've been knocked out of 1st place in '{league.name}'.")

        except Exception as e:
            print(f"An unexpected error occurred during score update for tour '{tour}': {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()

        # --- Self-Rescheduling Logic ---
        now_utc = datetime.now(timezone.utc)
        if now_utc < end_time:
            print(f"End time ({end_time}) not reached. Rescheduling task for tour '{tour}' in 3 minutes.")
            self.apply_async(args=[tour, end_time_iso], countdown=180) # 180 seconds = 3 minutes
        else:
            print(f"End time reached for tour '{tour}'. Stopping live score updates for the day.")


# --- REPLACEMENT 2: The Final schedule_score_updates_for_the_week Task ---
@shared_task
def schedule_score_updates_for_the_week():
    """
    Runs daily (Thu-Sun) at 5 AM. Finds today's tee times and kicks off
    the first self-repeating update_player_scores task for each active tour.
    """
    app = create_app()
    with app.app_context():
        print(f"--- Running DAILY scheduler setup at {datetime.now()} ---")
        tours = ['pga', 'euro']
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

            tee_time_key = f"r{current_round}_teetime"
            earliest_tee_time = None
            latest_tee_time = None

            for player in field_data['field']:
                tee_time_str = player.get(tee_time_key)
                if tee_time_str:
                    try:
                        tee_time = datetime.strptime(tee_time_str, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
                        if earliest_tee_time is None or tee_time < earliest_tee_time:
                            earliest_tee_time = tee_time
                        if latest_tee_time is None or tee_time > latest_tee_time:
                            latest_tee_time = tee_time
                    except (ValueError, TypeError):
                        continue # Ignore invalid tee time formats

            if earliest_tee_time and latest_tee_time:
                start_updates_at = earliest_tee_time + timedelta(minutes=20)
                end_updates_at = latest_tee_time + timedelta(hours=5)

                print(f"SUCCESS: Kicking off live updater for tour '{tour}'.")
                print(f"  > Updates will run from {start_updates_at} to {end_updates_at}")

                # Kick off the FIRST task in the chain. It will start at `start_updates_at`
                # and will know to stop itself after `end_updates_at`.
                update_player_scores.apply_async(
                    args=[tour, end_updates_at.isoformat()],
                    eta=start_updates_at
                )
            else:
                print(f"Could not determine tee times for tour '{tour}' for round {current_round}. No job scheduled.")

# --- Task to reset all player scores weekly ---
@shared_task
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

@shared_task
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
# def settle_finished_leagues(app):
#     """
#     This job runs periodically to perform a final score update for leagues
#     that have just ended.
#     """
#     with app.app_context():
#         now = datetime.utcnow()
#         # Look for leagues that ended in the last 15 minutes and are not yet finalized
#         recently_finished = now - timedelta(minutes=15)

#         leagues_to_settle = League.query.filter(
#             League.end_date.between(recently_finished, now),
#             League.is_finalized == False
#         ).all()

#         if not leagues_to_settle:
#             print(f"--- No leagues to settle at {datetime.now()} ---")
#             return

#         print(f"--- Found {len(leagues_to_settle)} league(s) to settle. Performing final score update. ---")

#         API_KEY = app.config['DATA_GOLF_API_KEY']
#         # The pre-tournament endpoint also contains the final results after an event.
#         url = f"https://feeds.datagolf.com/preds/pre-tournament?tour=pga&odds_format=decimal&key={API_KEY}"

#         try:
#             response = requests.get(url)
#             response.raise_for_status()
#             data = response.json()

#             # We create a dictionary of player scores for quick lookup
#             player_scores = {}
#             for api_player in data.get('field', []):
#                 player_name_parts = api_player.get('player_name', '').split(', ')
#                 if len(player_name_parts) == 2:
#                     surname, name = player_name_parts[0].strip(), player_name_parts[1].strip()
#                     # Create a unique key for the dictionary
#                     player_key = f"{name.lower()} {surname.lower()}"
#                     player_scores[player_key] = api_player.get('to_par', 0)

#             if not player_scores:
#                 print("Could not fetch final player scores from API.")
#                 return

#             # Get all players from our database
#             all_db_players = Player.query.all()
#             updated_count = 0
#             for player in all_db_players:
#                 player_key = f"{player.name.lower()} {player.surname.lower()}"
#                 if player_key in player_scores:
#                     player.current_score = player_scores[player_key]
#                     updated_count += 1

#             db.session.commit()
#             print(f"Final scores updated for {updated_count} players.")

#         except requests.exceptions.RequestException as e:
#             print(f"Error fetching final scores from API: {e}")

@shared_task(bind=True)
def collect_league_fees(self, league_id):
    """
    Calculates and collects the application fees for all entries in a league
    by creating a direct charge on the club's Stripe account.
    """
    app = create_app()
    with app.app_context():
        try:
            league = League.query.get(league_id)
            if not league:
                logging.error(f"League with ID {league_id} not found.")
                return

            club = league.club
            if not club or not club.stripe_account_id:
                logging.error(f"Club for league {league.id} not found or has no Stripe account.")
                return

            # Find entries where the fee hasn't been collected
            entries_to_charge = LeagueEntry.query.filter_by(
                league_id=league.id,
                fee_collected=False
            ).all()

            if not entries_to_charge:
                logging.info(f"No fees to collect for league {league.id}.")
                return

            num_entries = len(entries_to_charge)
            application_fee_per_entry = 250  # €2.50 in cents
            total_fee_to_collect = num_entries * application_fee_per_entry

            # Create a direct charge on the club's account
            # This pulls funds FROM the club's Stripe account TO the platform account
            stripe.api_key = current_app.config['STRIPE_SECRET_KEY']

            # charge = stripe.Charge.create(
            #     amount=total_fee_to_collect,
            #     currency='eur',
            #     description=f"Application fees for {num_entries} entries in '{league.name}'",
            #     source=club.stripe_account_id,  # This is incorrect for direct charges, corrected below.
            #     # For Connected Accounts, you charge the platform and transfer from the connected account
            #     # The correct way is to create a transfer from the connected account.
            # )

            # Correction for charging connected accounts: Create a Transfer, not a Charge.
            # This pulls funds from the connected account to your platform's balance.
            transfer = stripe.Transfer.create(
                amount=total_fee_to_collect,
                currency='eur',
                destination=current_app.config['STRIPE_PLATFORM_ACCOUNT_ID'], # You need to store your own account ID
                transfer_group=f"league-{league.id}-fees",
                # The source of the funds is implicitly the connected account's balance
                stripe_account=club.stripe_account_id,
            )


            # Mark fees as collected
            for entry in entries_to_charge:
                entry.fee_collected = True

            db.session.commit()
            logging.info(f"Successfully collected €{total_fee_to_collect / 100:.2f} for {num_entries} entries in league {league.id}.")

        except stripe.error.StripeError as e:
            logging.error(f"Stripe error while collecting fees for league {league.id}: {e}")
            # Optionally, you can retry the task
            # self.retry(exc=e, countdown=60)
        except Exception as e:
            logging.error(f"An unexpected error occurred while collecting fees for league {league.id}: {e}")
            # self.retry(exc=e, countdown=60)


@shared_task(bind=True)
def check_and_queue_fee_collection(self):
    """
    Runs daily. Finds leagues that have started and for which fees have not
    yet been processed, then queues the collection task for each.
    """
    app = create_app()
    with app.app_context():
        logging.info("Scheduler starting: Checking for leagues to process fees...")
        today = date.today()

        leagues_to_process = League.query.filter(
            League.start_date <= today,
            League.fees_processed == False
        ).all()

        if not leagues_to_process:
            logging.info("No new leagues found for fee processing.")
            return

        for league in leagues_to_process:
            logging.info(f"Queueing fee collection for league: {league.name} (ID: {league.id})")

            # Mark as processed immediately to prevent duplicate processing
            league.fees_processed = True
            db.session.add(league)

            # Dispatch the actual fee collection task to a worker
            collect_league_fees.delay(league.id)

        db.session.commit()
        logging.info(f"Successfully queued fee collection for {len(leagues_to_process)} leagues.")

# In fantasy_league_app/tasks.py
@shared_task
def update_player_buckets(app):
    """
    Scheduled task to create new player buckets for upcoming tournaments.
    It fetches the tournament field and the latest betting odds,
    applies a cap to the odds, and populates the bucket.
    """
    with app.app_context():
        print("--- Running scheduled job: update_player_buckets ---")
        tours = ['pga', 'euro']
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
            odds_map = {player['dg_id']: player.get('bet365') for player in odds_data}

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
                    if odds_from_api > 250:
                        player.odds = 250
                    elif odds_from_api < 1:
                        player.odds = 250
                    else:
                        player.odds = odds_from_api
                else:
                    # Set a high default for players without odds so they can still be picked
                    player.odds = 250

                latest_bucket.players.append(player)

        db.session.commit()
        print("--- Player bucket update finished successfully. ---")


@shared_task
def finalize_finished_leagues():
    """
    Finds all leagues that have ended but are not yet finalized, calculates
    winners for each, and sends email notifications.
    """
    app = create_app()
    with app.app_context():
        now = datetime.utcnow()

        # 1. Find all leagues that are ready to be finalized
        leagues_to_finalize = League.query.filter(
            League.end_date <= now,
            League.is_finalized == False
        ).all()

        if not leagues_to_finalize:
            print("No leagues found to finalize at this time.")
            return "No leagues to finalize."

        finalized_count = 0
        # 2. Loop through each league and process it
        for league in leagues_to_finalize:
            print(f"--- Finalizing league: {league.name} (ID: {league.id}) ---")

            entries = league.entries
            if not entries:
                print(f"No entries found for League {league.id}. Skipping.")
                league.is_finalized = True # Mark as finalized to prevent reprocessing
                db.session.add(league)
                continue # Move to the next league

            # --- Calculate Final Scores ---
            historical_scores = {score.player_id: score.score for score in PlayerScore.query.filter_by(league_id=league.id).all()}
            for entry in entries:
                score1 = historical_scores.get(entry.player1_id, 0)
                score2 = historical_scores.get(entry.player2_id, 0)
                score3 = historical_scores.get(entry.player3_id, 0)
                entry.total_score = score1 + score2 + score3

            # --- Determine the Winner(s) with Tie-Breaker Logic ---
            min_score = min(entry.total_score for entry in entries if entry.total_score is not None)
            top_entries = [entry for entry in entries if entry.total_score == min_score]

            winners = []
            if len(top_entries) == 1:
                winners = [top_entries[0].user]
            else:
                actual_answer = league.tie_breaker_actual_answer
                if actual_answer is not None:
                    min_diff = min(abs(e.tie_breaker_answer - actual_answer) for e in top_entries if e.tie_breaker_answer is not None)
                    winners = [e.user for e in top_entries if e.tie_breaker_answer is not None and abs(e.tie_breaker_answer - actual_answer) == min_diff]
                    if not winners: # If no one submitted a tie-breaker answer, all are winners
                        winners = [e.user for e in top_entries]
                else: # If no actual answer was set, all tied entries are winners
                    winners = [e.user for e in top_entries]

            # --- Assign Winners and Finalize League ---
            league.winners = winners
            league.is_finalized = True
            db.session.add(league)
            finalized_count += 1

            # --- Notify the Club Owner ---
            club_owner = league.club
            if club_owner and club_owner.email and winners:
                subject = f"Winner(s) Declared for Your League: {league.name}"
                winner_details_html = "<ul>" + "".join(
                    f"""<li>
                        <strong>Name:</strong> {winner.full_name} <br>
                        <strong>Email:</strong> {winner.email} <br>
                        <strong>Score:</strong> {next((e.total_score for e in top_entries if e.user_id == winner.id), 'N/A')}
                    </li>""" for winner in winners
                ) + "</ul>"
                html_body = f"""
                <p>Hello {club_owner.club_name},</p>
                <p>Your fantasy league, <strong>{league.name}</strong>, has concluded and the winner(s) have been determined.</p>
                <h3>Winner Details:</h3>
                {winner_details_html}
                <p>You are now responsible for arranging the prize payout to the winner(s).</p>
                """
                send_email(subject=subject, recipients=[club_owner.email], html_body=html_body)
                print(f"Successfully sent winner notification for League {league.id}.")

        # 3. Commit all changes to the database at once
        db.session.commit()
        return f"Successfully finalized {finalized_count} league(s)."

# @shared_task
# def finalize_finished_leagues():
#     """
#     This task is triggered when a league's tournament is over. It calculates the
#     final scores, determines the winner(s) using tie-breaker logic, and sends an
#     email notification to the club that hosted the league.
#     """
#     # --- 1. Get the League and its Entries ---
#     leagues_to_finalize = League.query.filter(
#             League.end_date <= now,
#             League.is_finalized == False
#         ).all()
#     if not league or not league.is_finalized:
#         print(f"League {league_id} not found or not ready for finalization.")
#         return

#     entries = LeagueEntry.query.filter_by(league_id=league.id).all()
#     if not entries:
#         print(f"No entries found for League {league_id}. Nothing to do.")
#         return

#     # --- 2. Calculate Final Scores ---
#     historical_scores = {score.player_id: score.score for score in PlayerScore.query.filter_by(league_id=league.id).all()}

#     for entry in entries:
#         score1 = historical_scores.get(entry.player1_id, 0)
#         score2 = historical_scores.get(entry.player2_id, 0)
#         score3 = historical_scores.get(entry.player3_id, 0)
#         entry.total_score = score1 + score2 + score3

#     # --- 3. Determine the Winner(s) with Tie-Breaker Logic ---

#     # In golf, the lowest score wins.
#     min_score = min(entry.total_score for entry in entries if entry.total_score is not None)
#     top_entries = [entry for entry in entries if entry.total_score == min_score]

#     winners = []
#     if len(top_entries) == 1:
#         # A single, clear winner
#         winners = [top_entries[0].user]
#     else:
#         # Multiple entries are tied, use the tie-breaker
#         actual_answer = league.tie_breaker_actual_answer
#         if actual_answer is not None:
#             # Find the entry with the smallest difference to the actual answer
#             min_diff = float('inf')
#             for e in top_entries:
#                 if e.tie_breaker_answer is not None:
#                     diff = abs(e.tie_breaker_answer - actual_answer)
#                     if diff < min_diff:
#                         min_diff = diff

#             # Find all entries that match this minimum difference
#             winners = [e.user for e in top_entries if e.tie_breaker_answer is not None and abs(e.tie_breaker_answer - actual_answer) == min_diff]

#             # If no one submitted a tie-breaker answer, all are winners
#             if not winners:
#                 winners = [e.user for e in top_entries]
#         else:
#             # If no actual answer was set, all tied entries are winners
#             winners = [e.user for e in top_entries]

#     # Assign the list of winners to the league's winner relationship
#     league.winners = winners
#     db.session.commit()

#     # --- 4. Notify the Club Owner ---
#     club_owner = league.club_host
#     if club_owner and club_owner.email and winners:
#         subject = f"Winner(s) Declared for Your League: {league.name}"

#         # Format the winner details for the email
#         winner_details_html = "<ul>"
#         for winner_user in winners:
#             winner_entry = next((e for e in top_entries if e.user_id == winner_user.id), None)
#             winner_details_html += f"""
#                 <li>
#                     <strong>Winner's Name:</strong> {winner_user.full_name} <br>
#                     <strong>Winning Score:</strong> {winner_entry.total_score if winner_entry else 'N/A'} <br>
#                     <strong>Winner's Email:</strong> {winner_user.email}
#                 </li>
#             """
#         winner_details_html += "</ul>"

#         html_body = f"""
#         <p>Hello {club_owner.club_name},</p>
#         <p>Your fantasy league, <strong>{league.name}</strong>, has now concluded and the winner(s) have been determined.</p>
#         <hr>
#         <h3>Winner Details:</h3>
#         {winner_details_html}
#         <hr>
#         <p>You are now responsible for arranging the prize payout to the winner(s) directly.</p>
#         <p>Thank you for using Fantasy Fairways.</p>
#         """

#         send_email(
#             subject=subject,
#             recipients=[club_owner.email],
#             html_body=html_body
#         )

#         print(f"Successfully sent winner notification email to {club_owner.email} for League {league.id}.")
#     else:
#         print(f"Could not send notification for League {league.id}: Club owner, email, or winner not found.")

#     return f"League {league.id} finalized. Winners determined. Notification sent to club."

@shared_task
def broadcast_notification_task(app, title, body):
    """
    Background task to send a push notification to ALL subscribed users.
    """
    with app.app_context():
        print(f"--- Starting broadcast task: '{title}' ---")
        # Fetch all active users who might have subscriptions
        all_users = User.query.filter_by(is_active=True).all()
        user_ids = [user.id for user in all_users]

        # Send a notification to each user
        # The send_push_notification helper already handles finding all devices for a user
        for user_id in user_ids:
            send_push_notification(user_id, title, body)

        print(f"--- Broadcast task finished. Notifications sent to {len(user_ids)} users. ---")