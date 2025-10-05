import logging
from fantasy_league_app.extensions import db, celery
from datetime import datetime, timedelta, timezone, date
from collections import defaultdict
import requests
import os
from sqlalchemy import func
from typing import Dict, List, Optional, Any
from fantasy_league_app.push.models import NotificationLog, NotificationTemplate
from . import mail, socketio, get_app, cache    # Make sure mail is imported if you use it in other tasks
from flask_mail import Message
from flask import current_app
from fantasy_league_app.push.services import push_service, send_rank_change_notification, send_tournament_start_notification
from .data_golf_client import DataGolfClient

from collections import defaultdict # Add this import
from .models import League, Player, PlayerBucket, LeagueEntry, PlayerScore, User, PushSubscription, db, DailyTaskTracker
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from .stripe_client import process_payouts,  create_payout
from .utils import send_winner_notification_email, send_push_notification, send_email, send_big_mover_email, send_big_drop_email,send_leader_email, send_leader_lost_email
from requests.exceptions import RequestException, Timeout,ConnectionError

class CacheManager:
    @staticmethod
    def cache_key_for_player_scores(tour):
        return f"player_scores_{tour}"

    @staticmethod
    def cache_key_for_leaderboard(league_id):
        return f"leaderboard_{league_id}"

# Custom exceptions for better error handling
class TemporaryAPIError(Exception):
    """Temporary API error that should trigger retry"""
    pass

class PermanentAPIError(Exception):
    """Permanent API error that should not retry"""
    pass

class DatabaseConnectionError(Exception):
    """Database connection error that should trigger retry"""
    pass

# Set up proper logging for Celery tasks
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


###########################
###########################
#####DEBUGGING#############
###########################
###########################

@shared_task
def simple_test_task(message):
    """Very simple test task that doesn't need app context"""
    import time

    print(f"🚀 SIMPLE TASK STARTED: {message}")
    print(f"🚀 Current time: {datetime.now()}")
    print(f"🚀 Task is running successfully!")

    # Small delay to see it's working
    time.sleep(2)

    result = f"Simple task completed at {datetime.now()} with message: {message}"
    print(f"🚀 SIMPLE TASK FINISHED: {result}")

    return result

# Also fix your test_celery_connection task to be more verbose
@shared_task
def test_celery_connection():
    """Simple test task to verify Celery is working"""
    print("=" * 50)
    print("🧪 TEST TASK STARTING!")
    print(f"🧪 Current time: {datetime.utcnow()}")
    print(f"🧪 Today: {date.today()}")
    print(f"🧪 Weekday: {date.today().weekday()}")

    # Test app context
    try:
        app = get_app()
        with app.app_context():
            print("🧪 App context is working!")
            # Try a simple DB query
            from .models import User
            user_count = User.query.count()
            print(f"🧪 Database connection working! User count: {user_count}")
    except Exception as e:
        print(f"🧪 ERROR with app context: {e}")
        return f"App context failed: {str(e)}"

    result = f"Test successful at {datetime.utcnow()}"
    print(f"🧪 TEST TASK FINISHED: {result}")
    print("=" * 50)

    return result


###########################
###########################
#####END DEBUGGING#########
###########################
###########################

def invalidate_score_caches(tour):
    """Invalidate score-related caches when scores update"""
    # Clear player scores cache
    score_key = CacheManager.cache_key_for_player_scores(tour)
    cache.delete(score_key)

    # Clear leaderboards for leagues on this tour
    active_leagues = League.query.filter(
        League.tour == tour,
        League.is_finalized == False
    ).all()

    for league in active_leagues:
        league.invalidate_cache()

@shared_task(bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    soft_time_limit=300,  # 5 minute soft limit
    time_limit=360)
def update_player_scores(self, tour, end_time_iso):
    """
    Fetches live scores for a tour, updates the database, calculates rank changes,
    and reschedules itself to run again every 3 minutes until the end_time is reached.
    """
    app = get_app()
    try:
        with app.app_context():
            logger.info(f"Starting score update for tour '{tour}' (attempt {self.request.retries + 1})")

            # Convert the end_time string back to a timezone-aware datetime object
            end_time = datetime.fromisoformat(end_time_iso).replace(tzinfo=timezone.utc)

            try:
                data_golf_client = DataGolfClient()
                in_play_stats, error = data_golf_client.get_in_play_stats(tour)

                if error:
                    if "rate limit" in error.lower() or "429" in error:
                        logger.warning(f"API rate limit hit for tour {tour}")
                        raise TemporaryAPIError(f"Rate limit error: {error}")
                    elif "500" in error or "502" in error or "503" in error:
                        logger.warning(f"Server error from API for tour {tour}")
                        raise TemporaryAPIError(f"Server error: {error}")
                    else:
                        logger.error(f"Permanent API error for tour {tour}: {error}")
                        raise PermanentAPIError(f"API error: {error}")

                if not in_play_stats or not isinstance(in_play_stats, list):
                    logger.warning(f"No valid data received for tour {tour}")
                    return f"No data available for tour {tour}"

                # Process the data with error handling
                player_scores_from_api = {player['dg_id']: player for player in in_play_stats}
                player_dg_ids = list(player_scores_from_api.keys())

                # Database operations with error handling
                try:
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

                    # Update player scores
                    players_in_db = Player.query.filter(Player.dg_id.in_(player_dg_ids)).all()
                    players_to_update = []

                    for player in players_in_db:
                        score_data = player_scores_from_api.get(player.dg_id)
                        if score_data:
                            new_score = score_data.get('current_score')
                            player_pos = score_data.get('current_pos', '').upper()

                            if new_score is not None and player_pos in ['WD', 'CUT', 'DF']:
                                new_score += 10
                                logger.info(f"Applying +10 penalty to {player.full_name} for status: {player_pos}")

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
                        # INVALIDATE CACHES AFTER SCORE UPDATE
                        invalidate_score_caches(tour)
                        logger.info(f"Successfully updated {len(players_to_update)} players for tour: '{tour}'")
                        socketio.emit('scores_updated', {'updated_tours': [tour]})

                        # Send notifications for rank changes
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
                                    # Big positive movement (5+ positions up)
                                    if (old_rank - new_rank) >= 5:
                                        send_big_mover_email(entry.user_id, new_rank, league.name)

                                    # Big negative movement (5+ positions down)
                                    elif (new_rank - old_rank) >= 5:
                                        send_big_drop_email(entry.user_id, new_rank, league.name)

                                    # Moved into 1st place
                                    elif new_rank == 1 and old_rank != 1:
                                        send_leader_email(entry.user_id, league.name)

                                    # Lost 1st place
                                    elif old_rank == 1 and new_rank != 1:
                                        send_leader_lost_email(entry.user_id, new_rank, league.name)

                except Exception as db_error:
                    logger.error(f"Database error during score update: {db_error}")
                    db.session.rollback()
                    raise DatabaseConnectionError(f"Database operation failed: {db_error}")

            except SoftTimeLimitExceeded:
                logger.warning(f"Task {self.request.id} approaching time limit, will retry")
                raise self.retry(countdown=180)  # Retry in 3 minutes

            # Self-rescheduling logic
            now_utc = datetime.now(timezone.utc)

            active_leagues = League.query.filter(
            League.tour == tour,
            League.is_finalized == False,
            League.end_date > now_utc).count()

            if active_leagues > 0 and now_utc < end_time:
                logger.info(f"Rescheduling task for tour '{tour}' - {active_leagues} leagues still active")
                self.apply_async(args=[tour, end_time_iso], countdown=180)
            else:
                logger.info(f"Stopping updates for tour '{tour}' - no active leagues or past end time")

            return f"Score update completed for tour {tour}"

    except PermanentAPIError as e:
        logger.error(f"Permanent error for tour {tour}: {e}")
        return f"Permanent failure for tour {tour}: {str(e)}"

    except Exception as e:
        logger.error(f"Unexpected error in score update for tour {tour}: {e}")
        raise  # Let Celery handle the retry


@shared_task(
    bind=True,
    autoretry_for=(DatabaseConnectionError, RequestException),
    retry_kwargs={'max_retries': 2, 'countdown': 30},
    soft_time_limit=60,   # 1 minute
    time_limit=90         # 1.5 minutes
)
def ensure_live_updates_are_running(self):
    """
    A supervisor task that runs frequently on tournament days.
    It checks if the main 5 AM scheduler has run and, if not, triggers it.
    """

    # STEP 1: Log that the task is actually running
    logger.info("=" * 60)
    logger.info("SUPERVISOR TASK STARTED")
    logger.info(f"UTC Time: {datetime.utcnow()}")
    logger.info("=" * 60)

    app = get_app()
    try:
        with app.app_context():
            logger.info(f"SUPERVISOR: Starting check (attempt {self.request.retries + 1})")

            today = date.today()
            weekday = today.weekday()

            if 3 <= weekday <= 6:  # Tournament days
                try:
                    task_ran_today = DailyTaskTracker.query.filter_by(
                        task_name='schedule_score_updates',
                        run_date=today
                    ).first()

                    if task_ran_today:
                        logger.info(f"SUPERVISOR: 5 AM job already ran today")
                    else:
                        logger.warning(f"SUPERVISOR: Triggering missed 5 AM job")
                        from .tasks import schedule_score_updates_for_the_week
                        result = schedule_score_updates_for_the_week.delay()
                        logger.info(f"SUPERVISOR: Triggered job {result.id}")

                except Exception as db_error:
                    logger.error(f"SUPERVISOR: Database error: {db_error}")
                    raise DatabaseConnectionError(f"Database query failed: {db_error}")
            else:
                logger.info(f"SUPERVISOR: Not a tournament day")

            return f"Supervisor check completed for {today}"

    except SoftTimeLimitExceeded:
        logger.warning("SUPERVISOR: Task timeout, will retry")
        raise self.retry(countdown=60)
    except Exception as e:
        logger.error(f"SUPERVISOR: Unexpected error: {e}")
        raise


@shared_task
def test_celery_connection():
    """Simple test task to verify Celery is working"""
    logger.info("🧪 TEST TASK RUNNING!")
    logger.info(f"Current time: {datetime.utcnow()}")
    logger.info(f"Today: {date.today()}")
    logger.info(f"Weekday: {date.today().weekday()}")
    return f"Test successful at {datetime.utcnow()}"


# DEBUG HELPER: Manual trigger function
@shared_task
def debug_trigger_supervisor():
    """Manual debug task to trigger supervisor logic"""
    logger.info("🔧 DEBUG: Manually triggering supervisor logic")

    # Call the supervisor task directly
    result = ensure_live_updates_are_running.delay()
    logger.info(f"🔧 DEBUG: Supervisor task result: {result.id}")

    # Also call the main scheduler
    result2 = schedule_score_updates_for_the_week.delay()
    logger.info(f"🔧 DEBUG: Main scheduler result: {result2.id}")

    return f"Debug triggered: supervisor={result.id}, scheduler={result2.id}"


# VERIFICATION TASK: Check what's in the beat schedule
@shared_task
def debug_list_scheduled_tasks():
    """Debug task to show all scheduled tasks"""
    from celery import current_app as celery_app

    logger.info("📋 SCHEDULED TASKS DEBUG:")
    logger.info("=" * 50)

    if hasattr(celery_app.conf, 'beat_schedule'):
        for task_name, task_config in celery_app.conf.beat_schedule.items():
            logger.info(f"Task: {task_name}")
            logger.info(f"  - Function: {task_config.get('task')}")
            logger.info(f"  - Schedule: {task_config.get('schedule')}")
            logger.info("-" * 30)
    else:
        logger.warning("No beat_schedule found in Celery config!")

    return "Debug info logged"


@shared_task(
    bind=True,
    autoretry_for=(DatabaseConnectionError, RequestException),
    retry_kwargs={'max_retries': 2, 'countdown': 120},
    soft_time_limit=600,  # 10 minutes
    time_limit=720        # 12 minutes
)
def schedule_score_updates_for_the_week(self):
    """
    Runs daily (Thu-Sun) at 5 AM. Finds today's tee times and kicks off
    the first self-repeating update_player_scores task for each active tour.
    """
    app = get_app()
    try:
        with app.app_context():
            logger.info(f"SCHEDULER: Starting setup (attempt {self.request.retries + 1})")

            today = date.today()

            try:
                # Check if already run
                task_tracker = DailyTaskTracker.query.filter_by(
                    run_date=today,
                    task_name='schedule_score_updates'
                ).first()

                if not task_tracker:
                    new_tracker = DailyTaskTracker(
                        task_name='schedule_score_updates',
                        run_date=today
                    )
                    db.session.add(new_tracker)
                    db.session.commit()

            except Exception as db_error:
                logger.error(f"SCHEDULER: Database error: {db_error}")
                raise DatabaseConnectionError(f"Task tracker error: {db_error}")

            tours = ['pga', 'euro']
            data_golf_client = DataGolfClient()

            for tour in tours:
                try:
                    logger.info(f"SCHEDULER: Processing tour {tour}")

                    field_data, field_error = data_golf_client.get_tournament_field_updates(tour)
                    if field_error:
                        if "rate limit" in field_error.lower():
                            raise TemporaryAPIError(f"Rate limit for {tour}: {field_error}")
                        else:
                            logger.warning(f"SCHEDULER: API error for {tour}: {field_error}")
                            continue

                    if not field_data or not field_data.get('field'):
                        logger.info(f"SCHEDULER: No field data for {tour}")
                        continue

                    current_round = field_data.get("current_round")
                    if not current_round:
                        logger.info(f"SCHEDULER: No current round for {tour}")
                        continue

                    # Process tee times
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
                                continue

                    if earliest_tee_time and latest_tee_time:
                        start_updates_at = earliest_tee_time + timedelta(minutes=20)
                        end_updates_at = latest_tee_time + timedelta(hours=5)

                        logger.info(f"SCHEDULER: Scheduling {tour} updates from {start_updates_at} to {end_updates_at}")

                        update_player_scores.apply_async(
                            args=[tour, end_updates_at.isoformat()],
                            eta=start_updates_at
                        )
                    else:
                        logger.warning(f"SCHEDULER: No tee times found for {tour}")

                except SoftTimeLimitExceeded:
                    logger.warning(f"SCHEDULER: Timeout processing {tour}")
                    raise self.retry(countdown=300)
                except Exception as tour_error:
                    logger.error(f"SCHEDULER: Error processing {tour}: {tour_error}")
                    # Continue with next tour rather than failing entire task
                    continue

            return "Scheduler setup completed"

    except Exception as e:
        logger.error(f"SCHEDULER: Unexpected error: {e}")
        raise

# --- Task to reset all player scores weekly ---
@shared_task(
    autoretry_for=(DatabaseConnectionError,),
    retry_kwargs={'max_retries': 2, 'countdown': 120},
    soft_time_limit=300,
    time_limit=360
)
def reset_player_scores():  # Removed self parameter
    """
    Scheduled to run weekly to reset the 'current_score' for all players to 0.
    """
    print(f"--- Running weekly player score reset at {datetime.now()} ---")

    app = get_app()
    try:
        with app.app_context():
            logger.info("RESET: Starting score reset")

            try:
                updated_rows = db.session.query(Player).update({"current_score": 0})
                db.session.commit()
                logger.info(f"RESET: Successfully reset {updated_rows} player scores")

                # Send notifications
                all_users = User.query.filter_by(is_active=True).yield_per(100)
                notification_count = 0

                for user in all_users:
                    try:
                        send_push_notification(
                            user.id,
                            "New Week, New Leagues!",
                            "Player data has been updated. Check out the new leagues for this week's tournaments."
                        )
                        notification_count += 1
                    except Exception as notif_error:
                        logger.warning(f"RESET: Failed to send notification to user {user.id}: {notif_error}")
                        continue

                logger.info(f"RESET: Sent {notification_count} notifications")
                return f"Reset {updated_rows} scores, sent {notification_count} notifications"

            except Exception as db_error:
                logger.error(f"RESET: Database error: {db_error}")
                db.session.rollback()
                raise DatabaseConnectionError(f"Score reset failed: {db_error}")

    except Exception as e:
        logger.error(f"RESET: Unexpected error: {e}")
        rais

@shared_task
def send_deadline_reminders():
    """
    Runs periodically to send reminders for leagues whose entry deadline is approaching.
    """
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

@shared_task(bind=True)
def collect_league_fees(self, league_id):
    """
    Calculates and collects the application fees for all entries in a league
    by creating a direct charge on the club's Stripe account.
    """
    app = get_app()
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
    app = get_app()
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

@shared_task(
    bind=True,
    autoretry_for=(DatabaseConnectionError, RequestException),
    retry_kwargs={'max_retries': 3, 'countdown': 300},
    soft_time_limit=1800,  # 30 minutes
    time_limit=2100        # 35 minutes
)
def update_player_buckets(self):
    """
    Scheduled task to create new player buckets for upcoming tournaments.
    It fetches the tournament field and the latest betting odds,
    applies a cap to the odds, and populates the bucket.
    """
    print("--- Running scheduled job: update_player_buckets ---")



    app = get_app()
    try:
        with app.app_context():
            logger.info(f"BUCKET UPDATE: Starting (attempt {self.request.retries + 1})")

            tours = ['pga', 'euro']
            data_golf_client = DataGolfClient()

            for tour in tours:
                try:
                    logger.info(f"BUCKET UPDATE: Processing {tour}")

                    field_data, field_error = data_golf_client.get_tournament_field_updates(tour)
                    odds_data, odds_error = data_golf_client.get_betting_odds(tour)

                    if field_error or odds_error:
                        if "rate limit" in (field_error or odds_error or "").lower():
                            raise TemporaryAPIError(f"Rate limit for {tour}")
                        logger.warning(f"BUCKET UPDATE: API errors for {tour}: {field_error}, {odds_error}")
                        continue

                    if not field_data or not field_data.get('field') or not odds_data:
                        logger.info(f"BUCKET UPDATE: Incomplete data for {tour}")
                        continue

                    # Process data
                    odds_map = {player['dg_id']: player.get('bet365') for player in odds_data}
                    bucket_name = f"{tour.upper()} Players - {field_data.get('event_name', datetime.utcnow().strftime('%Y-%m-%d'))}"

                    try:
                        latest_bucket = PlayerBucket.query.filter_by(name=bucket_name).first()
                        if not latest_bucket:
                            latest_bucket = PlayerBucket(name=bucket_name, tour=tour)
                            db.session.add(latest_bucket)
                            logger.info(f"BUCKET UPDATE: Created bucket {bucket_name}")
                        else:
                            logger.info(f"BUCKET UPDATE: Updating existing bucket {bucket_name}")
                            latest_bucket.players = []

                        # Process players
                        for player_data in field_data['field']:
                            player_dg_id = player_data.get('dg_id')
                            if not player_dg_id:
                                continue

                            player = Player.query.filter_by(dg_id=player_dg_id).first()
                            if not player:
                                player = Player(dg_id=player_dg_id)
                                db.session.add(player)

                            # Update player details
                            player_name_parts = player_data.get('player_name', ',').split(',')
                            player.surname = player_name_parts[0].strip()
                            player.name = player_name_parts[1].strip() if len(player_name_parts) > 1 else ''

                            # Set odds with validation
                            odds_from_api = odds_map.get(player_dg_id)
                            if odds_from_api and isinstance(odds_from_api, (int, float)):
                                if odds_from_api > 250:
                                    player.odds = 250
                                elif odds_from_api < 1:
                                    player.odds = 250
                                else:
                                    player.odds = odds_from_api
                            else:
                                player.odds = 250

                            latest_bucket.players.append(player)

                        db.session.commit()
                        logger.info(f"BUCKET UPDATE: Completed {tour} with {len(latest_bucket.players)} players")

                    except Exception as db_error:
                        logger.error(f"BUCKET UPDATE: Database error for {tour}: {db_error}")
                        db.session.rollback()
                        raise DatabaseConnectionError(f"Bucket update failed for {tour}: {db_error}")

                except SoftTimeLimitExceeded:
                    logger.warning(f"BUCKET UPDATE: Timeout processing {tour}")
                    raise self.retry(countdown=600)
                except Exception as tour_error:
                    logger.error(f"BUCKET UPDATE: Error processing {tour}: {tour_error}")
                    continue

            return "Player bucket update completed"

    except Exception as e:
        logger.error(f"BUCKET UPDATE: Unexpected error: {e}")
        raise

@shared_task(
    bind=True,
    autoretry_for=(DatabaseConnectionError,),
    retry_kwargs={'max_retries': 3, 'countdown': 300},
    soft_time_limit=600,
    time_limit=720
)
def substitute_withdrawn_players(self):
    """
    Check for withdrawn players and automatically substitute them if they haven't
    started playing (no score recorded yet).
    """
    app = get_app()

    try:
        with app.app_context():
            logger.info("WITHDRAWAL CHECK: Starting automatic substitution check")

            now = datetime.utcnow()

            # Get leagues where:
            # 1. Deadline has passed (entries locked)
            # 2. Tournament is ongoing
            # 3. League not finalized
            leagues = League.query.filter(
                League.entry_deadline < now,
                League.is_finalized == False
            ).all()

            logger.info(f"WITHDRAWAL CHECK: Found {len(leagues)} active leagues to check")

            for league in leagues:
                if not league.player_bucket:
                    continue

                logger.info(f"WITHDRAWAL CHECK: Checking league {league.id} - {league.name}")

                # Get tournament field data with scores
                data_golf_client = DataGolfClient()
                field_data, error = data_golf_client.get_tournament_field_updates(league.tour)

                if error or not field_data or not field_data.get('field'):
                    logger.warning(f"WITHDRAWAL CHECK: Could not get field data for {league.tour}")
                    continue

                active_field = field_data.get('field', [])

                # Create a map of player dg_id to their status/score
                field_status = {}
                for field_player in active_field:
                    dg_id = field_player.get('dg_id')
                    # Check if player has started playing (has a score or thru value)
                    has_started = field_player.get('current_score') is not None or field_player.get('thru') not in [None, 0, '-']
                    field_status[dg_id] = {
                        'in_field': True,
                        'has_started': has_started
                    }

                # Check each entry for withdrawn players
                for entry in league.entries:
                    substitutions_made = []

                    # Check each of the 3 players
                    for position in [1, 2, 3]:
                        player_id = getattr(entry, f'player{position}_id')
                        player = Player.query.get(player_id)

                        if not player:
                            continue

                        player_status = field_status.get(player.dg_id, {'in_field': False, 'has_started': False})

                        # Only substitute if:
                        # 1. Player is not in field (withdrawn)
                        # 2. Player hasn't started playing yet (no score)
                        if not player_status['in_field'] and not player_status['has_started']:
                            logger.info(f"WITHDRAWAL CHECK: Player {player.full_name()} withdrawn and hasn't started - eligible for substitution")

                            # Find replacement player
                            replacement = find_replacement_player(
                                entry,
                                player,
                                league.player_bucket.players,
                                active_field
                            )

                            if replacement:
                                setattr(entry, f'player{position}_id', replacement.id)
                                substitutions_made.append({
                                    'old': player.full_name(),
                                    'new': replacement.full_name(),
                                    'position': position
                                })
                                logger.info(f"WITHDRAWAL CHECK: Substituted {player.full_name()} with {replacement.full_name()}")
                        elif not player_status['in_field'] and player_status['has_started']:
                            logger.info(f"WITHDRAWAL CHECK: Player {player.full_name()} withdrawn but has started playing - no substitution")

                    if substitutions_made:
                        # Recalculate total odds
                        p1 = Player.query.get(entry.player1_id)
                        p2 = Player.query.get(entry.player2_id)
                        p3 = Player.query.get(entry.player3_id)
                        entry.total_odds = p1.odds + p2.odds + p3.odds

                        db.session.commit()

                        # Send notification to user
                        send_substitution_notification(entry.user, substitutions_made, league)

            logger.info("WITHDRAWAL CHECK: Completed automatic substitution check")
            return "Withdrawal check completed"

    except Exception as e:
        logger.error(f"WITHDRAWAL CHECK: Error during substitution check: {e}")
        raise

def find_replacement_player(entry, withdrawn_player, bucket_players, active_field):
    """
    Find a suitable replacement player with similar odds.

    Args:
        entry: The LeagueEntry being updated
        withdrawn_player: The Player who withdrew
        bucket_players: List of all players in the bucket
        active_field: List of active players in the tournament

    Returns:
        Player object or None
    """
    import random

    # Get currently selected player IDs
    selected_ids = [entry.player1_id, entry.player2_id, entry.player3_id]

    # Get active player IDs from field
    active_player_dg_ids = [p.get('dg_id') for p in active_field]

    # Filter available players:
    # 1. Not already selected in this entry
    # 2. Still in the tournament field
    # 3. Not the withdrawn player
    available_players = [
        p for p in bucket_players
        if p.id not in selected_ids
        and p.dg_id in active_player_dg_ids
        and p.id != withdrawn_player.id
    ]

    if not available_players:
        logger.warning(f"No available replacement players for {withdrawn_player.full_name()}")
        return None

    # Find players with similar odds (within 20% range)
    withdrawn_odds = withdrawn_player.odds
    odds_range = withdrawn_odds * 0.2  # 20% range

    similar_odds_players = [
        p for p in available_players
        if abs(p.odds - withdrawn_odds) <= odds_range
    ]

    # If we have players with similar odds, randomly pick one
    if similar_odds_players:
        return random.choice(similar_odds_players)

    # Otherwise, pick the closest odds player
    return min(available_players, key=lambda p: abs(p.odds - withdrawn_odds))


def send_substitution_notification(user, substitutions, league):
    """Send notification to user about automatic substitutions"""
    try:
        substitution_text = "\n".join([
            f"Player {s['position']}: {s['old']} → {s['new']}"
            for s in substitutions
        ])

        subject = f"Player Substitution in {league.name}"
        body = f"""
Hello {user.full_name},

One or more players in your entry for "{league.name}" have withdrawn from the tournament.
We've automatically substituted them with players of similar odds:

{substitution_text}

Your updated team is now active for the tournament.

Good luck!

Fantasy Fairway Team
        """

        # Send email using your existing mail setup
        from flask_mail import Message
        from fantasy_league_app.extensions import mail

        msg = Message(
            subject=subject,
            recipients=[user.email],
            body=body
        )
        mail.send(msg)

        logger.info(f"Sent substitution notification to {user.email}")

    except Exception as e:
        logger.error(f"Failed to send substitution notification: {e}")

@shared_task(
    bind=True,
    autoretry_for=(DatabaseConnectionError,),
    retry_kwargs={'max_retries': 2, 'countdown': 180},
    soft_time_limit=900,   # 15 minutes
    time_limit=1080        # 18 minutes
)
def finalize_finished_leagues(self):
    """
    Finds all leagues that have ended but are not yet finalized, calculates
    winners for each, and sends email notifications.
    """
    app = get_app()
    try:
        with app.app_context():
            logger.info(f"FINALIZE: Starting (attempt {self.request.retries + 1})")

            now = datetime.utcnow()

            try:
                leagues_to_finalize = League.query.filter(
                    League.end_date <= now,
                    League.is_finalized == False
                ).all()

            except Exception as db_error:
                logger.error(f"FINALIZE: Database query error: {db_error}")
                raise DatabaseConnectionError(f"Failed to query leagues: {db_error}")

            if not leagues_to_finalize:
                logger.info("FINALIZE: No leagues to finalize")
                return "No leagues to finalize"

            finalized_count = 0
            failed_leagues = []

            for league in leagues_to_finalize:
                try:
                    logger.info(f"FINALIZE: Processing league {league.name}")

                    entries = league.entries
                    if not entries:
                        logger.info(f"FINALIZE: No entries for league {league.id}")
                        league.is_finalized = True
                        db.session.add(league)
                        continue

                    # Calculate final scores
                    historical_scores = {
                        score.player_id: score.score
                        for score in PlayerScore.query.filter_by(league_id=league.id).all()
                    }

                    for entry in entries:
                        score1 = historical_scores.get(entry.player1_id, 0)
                        score2 = historical_scores.get(entry.player2_id, 0)
                        score3 = historical_scores.get(entry.player3_id, 0)
                        entry.total_score = score1 + score2 + score3

                    # Determine winners
                    min_score = min(entry.total_score for entry in entries if entry.total_score is not None)
                    top_entries = [entry for entry in entries if entry.total_score == min_score]

                    winners = []
                    if len(top_entries) == 1:
                        winners = [top_entries[0].user]
                    else:
                        actual_answer = league.tie_breaker_actual_answer
                        if actual_answer is not None:
                            min_diff = min(
                                abs(e.tie_breaker_answer - actual_answer)
                                for e in top_entries
                                if e.tie_breaker_answer is not None
                            )
                            winners = [
                                e.user for e in top_entries
                                if e.tie_breaker_answer is not None
                                and abs(e.tie_breaker_answer - actual_answer) == min_diff
                            ]
                            if not winners:
                                winners = [e.user for e in top_entries]
                        else:
                            winners = [e.user for e in top_entries]

                    # Save results
                    league.winners = winners
                    league.is_finalized = True
                    db.session.add(league)

                    # Send notification
                    club_owner = league.club_host
                    if club_owner and club_owner.email and winners:
                        try:
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
                            <p>Your fantasy league, <strong>{league.name}</strong>, has concluded.</p>
                            <h3>Winner Details:</h3>
                            {winner_details_html}
                            <p>You are now responsible for arranging the prize payout to the winner(s).</p>
                            """

                            send_email(subject=subject, recipients=[club_owner.email], html_body=html_body)
                            logger.info(f"FINALIZE: Sent notification for league {league.id}")

                        except Exception as email_error:
                            logger.warning(f"FINALIZE: Failed to send email for league {league.id}: {email_error}")
                            # Don't fail the entire task for email issues

                    finalized_count += 1
                    logger.info(f"FINALIZE: Successfully finalized league {league.name}")

                except Exception as league_error:
                    logger.error(f"FINALIZE: Error processing league {league.id}: {league_error}")
                    failed_leagues.append(league.id)
                    # Continue with other leagues rather than failing entire task
                    continue

            try:
                db.session.commit()
                logger.info(f"FINALIZE: Committed {finalized_count} leagues")

            except Exception as commit_error:
                logger.error(f"FINALIZE: Commit error: {commit_error}")
                db.session.rollback()
                raise DatabaseConnectionError(f"Failed to commit league finalizations: {commit_error}")

            result = f"Finalized {finalized_count} leagues"
            if failed_leagues:
                result += f", failed: {failed_leagues}"

            return result

    except SoftTimeLimitExceeded:
        logger.warning("FINALIZE: Task timeout")
        raise self.retry(countdown=300)
    except Exception as e:
        logger.error(f"FINALIZE: Unexpected error: {e}")
        raise


@shared_task
def broadcast_notification_task(title, body):
    """
    Background task to send a push notification to ALL subscribed users.
    """
    print(f"--- Starting broadcast task: '{title}' ---")
    # Fetch all active users who might have subscriptions
    all_users = User.query.filter_by(is_active=True).yield_per(100)
    user_ids = [user.id for user in all_users]

    # Send a notification to each user
    # The send_push_notification helper already handles finding all devices for a user
    for user_id in user_ids:
        send_push_notification(user_id, title, body)

    print(f"--- Broadcast task finished. Notifications sent to {len(user_ids)} users. ---")


@shared_task
def warm_critical_caches():
    """Warm up critical caches during low-traffic periods"""
    from fantasy_league_app import create_app
    app = create_app()

    with app.app_context():
        logger.info("CACHE WARMING: Starting cache warm-up")

        try:
            # Warm up active leagues
            active_leagues = League.query.filter(
                League.is_finalized == False,
                League.start_date <= datetime.utcnow()
            ).all()

            for league in active_leagues:
                # Pre-populate leaderboard cache
                league.get_leaderboard()

            # Warm up player data for active tours
            for tour in ['pga', 'euro']:
                Player.get_players_by_tour_cached(tour)

            logger.info(f"CACHE WARMING: Completed for {len(active_leagues)} leagues")

        except Exception as e:
            logger.error(f"CACHE WARMING: Error: {e}")

@shared_task
def cleanup_expired_caches():
    """Clean up any manually tracked cache keys that might be stale"""
    app = get_app()

    with app.app_context():
        logger.info("CACHE CLEANUP: Starting cleanup")

        try:
            # Clean up leaderboard caches for finalized leagues
            finalized_leagues = League.query.filter(League.is_finalized == True).all()

            cleanup_count = 0
            for league in finalized_leagues:
                leaderboard_key = CacheManager.cache_key_for_leaderboard(league.id)
                if cache.get(leaderboard_key) is not None:
                    cache.delete(leaderboard_key)
                    cleanup_count += 1

            logger.info(f"CACHE CLEANUP: Cleaned {cleanup_count} stale cache entries")

        except Exception as e:
            logger.error(f"CACHE CLEANUP: Error: {e}")


@shared_task(
    bind=True,
    autoretry_for=(DatabaseConnectionError,),
    retry_kwargs={'max_retries': 2, 'countdown': 300},
    soft_time_limit=600,   # 10 minutes
    time_limit=720         # 12 minutes
)
def cleanup_expired_verification_tokens(self):

    """Clean up expired email verification tokens"""
    app = get_app()

    try:
        with app.app_context():
            logger.info("TOKEN CLEANUP: Starting expired token cleanup")

            from datetime import datetime, timedelta

            # Clean tokens older than 48 hours (keep for a bit longer than expiry)
            expired_cutoff = datetime.utcnow() - timedelta(hours=48)

            try:
                expired_users = User.query.filter(
                    User.email_verified == False,
                    User.email_verification_sent_at < expired_cutoff,
                    User.email_verification_token.isnot(None)
                ).all()

                count = 0
                for user in expired_users:
                    user.email_verification_token = None
                    user.email_verification_sent_at = None
                    count += 1

                db.session.commit()

                logger.info(f"TOKEN CLEANUP: Cleaned up {count} expired verification tokens")
                return f"Cleaned {count} expired tokens"

            except Exception as db_error:
                logger.error(f"TOKEN CLEANUP: Database error: {db_error}")
                db.session.rollback()
                raise DatabaseConnectionError(f"Token cleanup failed: {db_error}")

    except SoftTimeLimitExceeded:
        logger.warning("TOKEN CLEANUP: Task timeout")
        raise self.retry(countdown=300)
    except Exception as e:
        logger.error(f"TOKEN CLEANUP: Unexpected error: {e}")
        raise

@celery.task(bind=True)
def send_push_notification_task(
    self,
    user_ids: List[int],
    notification_type: str,
    title: str,
    body: str,
    data: Optional[Dict] = None,
    url: Optional[str] = None,
    icon: Optional[str] = None,
    badge: Optional[str] = None,
    actions: Optional[List[Dict]] = None,
    require_interaction: bool = False,
    tag: Optional[str] = None,
    vibrate: Optional[List[int]] = None
):
    """
    Celery task to send push notifications in the background
    Integrates with your existing task system
    """
    try:

        result = push_service.send_notification_sync(
            user_ids=user_ids,
            notification_type=notification_type,
            title=title,
            body=body,
            data=data,
            url=url,
            icon=icon,
            badge=badge,
            actions=actions,
            require_interaction=require_interaction,
            tag=tag,
            vibrate=vibrate
        )

        return {
            'task_id': self.request.id,
            'status': 'completed',
            **result
        }

    except Exception as e:
        self.retry(countdown=60, max_retries=3, exc=e)


@celery.task
def send_template_notification_task(
    user_ids: List[int],
    template_name: str,
    template_data: Dict[str, Any],
    **kwargs
):
    """Celery task to send template-based notifications"""
    try:

        return push_service.send_from_template(
            user_ids=user_ids,
            template_name=template_name,
            template_data=template_data,
            **kwargs
        )

    except Exception as e:
        # Log error and don't retry template notifications
        import logging
        logging.error(f"Template notification failed: {e}")
        return {'error': str(e), 'success': 0, 'failed': len(user_ids)}


@celery.task
def cleanup_old_push_subscriptions():
    """Celery task to cleanup old/inactive subscriptions"""
    from datetime import timedelta

    try:
        cutoff_date = datetime.utcnow() - timedelta(days=30)

        # Only cleanup if the model has these fields
        query = PushSubscription.query

        if hasattr(PushSubscription, 'last_used') and hasattr(PushSubscription, 'is_active'):
            old_subscriptions = query.filter(
                PushSubscription.last_used < cutoff_date,
                PushSubscription.is_active == False
            ).all()
        else:
            # Fallback: cleanup very old subscriptions
            if hasattr(PushSubscription, 'created_at'):
                very_old_date = datetime.utcnow() - timedelta(days=90)
                old_subscriptions = query.filter(
                    PushSubscription.created_at < very_old_date
                ).all()
            else:
                old_subscriptions = []

        count = len(old_subscriptions)
        for subscription in old_subscriptions:
            db.session.delete(subscription)

        db.session.commit()
        return f"Cleaned up {count} old push subscriptions"

    except Exception as e:
        db.session.rollback()
        return f"Failed to cleanup subscriptions: {e}"


@celery.task
def send_league_start_notifications():
    """Send notifications when leagues start (integrate with your existing schedule)"""
    try:


        # Get leagues starting today (adjust logic to match your needs)
        today = datetime.utcnow().date()
        starting_leagues = League.query.filter(
            db.func.date(League.start_date) == today,
            League.is_finalized == False
        ).all()

        notifications_sent = 0
        for league in starting_leagues:
            try:
                # Get all users in this league
                user_ids = [entry.user_id for entry in league.entries]

                if user_ids:
                    send_template_notification_task.delay(
                        user_ids=user_ids,
                        template_name='tournament_start',
                        template_data={
                            'tournament_name': league.name,
                            'league_id': league.id
                        },
                        url=f'/league/{league.id}'
                    )
                    notifications_sent += 1

            except Exception as e:
                print(f"Failed to send notification for league {league.id}: {e}")

        return f"Sent tournament start notifications for {notifications_sent} leagues"

    except Exception as e:
        return f"Failed to send league start notifications: {e}"


@celery.task
def send_rank_change_notifications():
    """
    Check for significant rank changes and send notifications
    This would integrate with your existing score update tasks
    """
    try:

        # This is pseudo-code - adapt to your rank change detection logic
        # You might call this after score updates

        notifications_sent = 0

        # Get active leagues
        active_leagues = League.query.filter_by(is_finalized=False).all()

        for league in active_leagues:
            try:
                # Get current leaderboard
                leaderboard = league.get_leaderboard()

                for entry_data in leaderboard:
                    user_id = entry_data['user_id']
                    current_rank = entry_data['position']

                    # Get entry to check previous rank
                    entry = LeagueEntry.query.filter_by(
                        league_id=league.id,
                        user_id=user_id
                    ).first()

                    if entry and hasattr(entry, 'previous_rank'):
                        previous_rank = entry.previous_rank

                        # Check for significant changes
                        if previous_rank and abs(previous_rank - current_rank) >= 5:
                            send_rank_change_notification(
                                user_id=user_id,
                                league_name=league.name,
                                new_rank=current_rank,
                                old_rank=previous_rank
                            )
                            notifications_sent += 1

                        # Update stored rank
                        if hasattr(entry, 'update_rank_if_changed'):
                            entry.update_rank_if_changed(current_rank)

            except Exception as e:
                print(f"Failed to process rank changes for league {league.id}: {e}")

        return f"Processed rank changes, sent {notifications_sent} notifications"

    except Exception as e:
        return f"Failed to process rank change notifications: {e}"


# Integration with your existing deadline reminder task
def enhance_send_deadline_reminders():
    """
    Example of how to add push notifications to your existing deadline reminder task
    Add this code to your existing send_deadline_reminders task
    """

    # Your existing email logic...

    # Add push notifications
    try:
        # Get leagues with upcoming deadlines (12-24 hours)
        from datetime import timedelta
        now = datetime.utcnow()
        deadline_start = now + timedelta(hours=12)
        deadline_end = now + timedelta(hours=24)

        upcoming_leagues = League.query.filter(
            League.entry_deadline >= deadline_start,
            League.entry_deadline <= deadline_end,
            League.is_finalized == False
        ).all()

        for league in upcoming_leagues:
            # Get users in this league
            user_ids = [entry.user_id for entry in league.entries]

            if user_ids:
                send_template_notification_task.delay(
                    user_ids=user_ids,
                    template_name='league_update',
                    template_data={
                        'message': f'Entry deadline for {league.name} is in 12 hours!'
                    },
                    url=f'/league/{league.id}'
                )

    except Exception as e:
        print(f"Failed to send push deadline reminders: {e}")


@shared_task
def send_deadline_urgent_alerts():
    """Send urgent alerts for leagues with approaching deadlines and filling spots"""
    app = get_app()

    with app.app_context():
        logger.info("DEADLINE ALERTS: Starting urgent deadline notifications")

        try:
            now = datetime.utcnow()

            # Find leagues with deadline in 1-3 hours
            deadline_start = now + timedelta(hours=1)
            deadline_end = now + timedelta(hours=3)

            urgent_leagues = League.query.filter(
                League.entry_deadline >= deadline_start,
                League.entry_deadline <= deadline_end,
                League.is_finalized == False
            ).all()

            notifications_sent = 0

            for league in urgent_leagues:
                # Calculate spots left
                max_entries = league.max_entries if hasattr(league, 'max_entries') else 50
                current_entries = len(league.entries)
                spots_left = max_entries - current_entries

                # Only alert if filling up (>50% full or <10 spots)
                if current_entries / max_entries < 0.5 and spots_left > 10:
                    continue

                # Calculate hours until deadline
                time_until = league.entry_deadline - now
                hours_left = int(time_until.total_seconds() / 3600)

                # Find users who might be interested but haven't joined
                # (users who joined similar leagues recently)
                similar_league_users = db.session.query(LeagueEntry.user_id).join(League).filter(
                    League.tour == league.tour,
                    League.entry_fee == league.entry_fee,
                    League.id != league.id,
                    League.start_date >= now - timedelta(days=30)
                ).distinct().all()

                # Exclude users already in this league
                already_in = [entry.user_id for entry in league.entries]
                potential_users = [
                    user_id[0] for user_id in similar_league_users
                    if user_id[0] not in already_in
                ]

                if potential_users:
                    send_template_notification_task.delay(
                        user_ids=potential_users[:20],  # Limit to 20 to avoid spam
                        template_name='deadline_urgent',
                        template_data={
                            'league_name': league.name,
                            'hours': hours_left,
                            'spots_left': spots_left
                        },
                        url=f'/league/{league.id}'
                    )
                    notifications_sent += len(potential_users[:20])

            logger.info(f"DEADLINE ALERTS: Sent {notifications_sent} urgent alerts")
            return f"Sent {notifications_sent} deadline alerts"

        except Exception as e:
            logger.error(f"DEADLINE ALERTS: Error: {e}")
            return f"Error: {e}"


@shared_task
def send_friend_joined_notifications():
    """Notify users when their friends join leagues"""
    app = get_app()

    with app.app_context():
        logger.info("FRIEND ALERTS: Starting friend activity notifications")

        try:
            # Get recent league joins (last 30 minutes)
            recent_time = datetime.utcnow() - timedelta(minutes=30)

            # You'll need to add a 'created_at' timestamp to LeagueEntry if you don't have one
            recent_entries = LeagueEntry.query.filter(
                LeagueEntry.created_at >= recent_time if hasattr(LeagueEntry, 'created_at') else True
            ).all()

            notifications_sent = 0

            for entry in recent_entries:
                league = entry.league
                user = entry.user

                # Find user's friends (you'll need to implement friendship system)
                # For now, we'll use users in same past leagues as proxy for "friends"
                friend_ids = db.session.query(LeagueEntry.user_id).join(League).filter(
                    League.id.in_(
                        db.session.query(League.id).join(LeagueEntry).filter(
                            LeagueEntry.user_id == user.id
                        )
                    ),
                    LeagueEntry.user_id != user.id
                ).distinct().limit(50).all()

                friend_ids = [f[0] for f in friend_ids]

                # Exclude friends already in this league
                already_in = [e.user_id for e in league.entries]
                friends_to_notify = [fid for fid in friend_ids if fid not in already_in]

                if friends_to_notify:
                    send_template_notification_task.delay(
                        user_ids=friends_to_notify,
                        template_name='friend_joined',
                        template_data={
                            'friend_name': user.full_name,
                            'league_name': league.name
                        },
                        url=f'/league/{league.id}'
                    )
                    notifications_sent += len(friends_to_notify)

            logger.info(f"FRIEND ALERTS: Sent {notifications_sent} notifications")
            return f"Sent {notifications_sent} friend activity alerts"

        except Exception as e:
            logger.error(f"FRIEND ALERTS: Error: {e}")
            return f"Error: {e}"


@shared_task
def send_tee_time_notifications():
    """Send notifications when user's players are about to tee off (20 min before)"""
    app = get_app()

    with app.app_context():
        logger.info("TEE TIME ALERTS: Starting tee time notifications")

        try:
            from datetime import datetime, timedelta

            # Get time window (next 15-25 minutes)
            now = datetime.utcnow()
            start_window = now + timedelta(minutes=15)
            end_window = now + timedelta(minutes=25)

            # Get active leagues
            active_leagues = League.query.filter(
                League.is_finalized == False,
                League.start_date <= now
            ).all()

            notifications_sent = 0

            for league in active_leagues:
                # Get tee times for this tour
                data_golf_client = DataGolfClient()
                field_data, error = data_golf_client.get_tournament_field_updates(league.tour)

                if error or not field_data:
                    continue

                current_round = field_data.get('current_round', 1)
                tee_time_key = f'r{current_round}_teetime'

                # Check each entry's players
                for entry in league.entries:
                    players_teeing_off = []

                    for player in [entry.player1, entry.player2, entry.player3]:
                        if not player:
                            continue

                        # Find player in field data
                        for field_player in field_data.get('field', []):
                            if field_player.get('dg_id') == player.dg_id:
                                tee_time_str = field_player.get(tee_time_key)

                                if tee_time_str:
                                    try:
                                        tee_time = datetime.strptime(tee_time_str, '%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
                                        tee_time_naive = tee_time.replace(tzinfo=None)

                                        # Check if within notification window
                                        if start_window <= tee_time_naive <= end_window:
                                            minutes_until = int((tee_time_naive - now).total_seconds() / 60)
                                            players_teeing_off.append({
                                                'name': player.full_name(),
                                                'minutes': minutes_until
                                            })
                                    except (ValueError, TypeError):
                                        continue

                    # Send notification if any players are teeing off soon
                    if players_teeing_off:
                        for player_info in players_teeing_off:
                            send_template_notification_task.delay(
                                user_ids=[entry.user_id],
                                template_name='player_teeing_off',
                                template_data={
                                    'player_name': player_info['name'],
                                    'minutes': player_info['minutes']
                                },
                                url=f'/league/{league.id}'
                            )
                            notifications_sent += 1

            logger.info(f"TEE TIME ALERTS: Sent {notifications_sent} notifications")
            return f"Sent {notifications_sent} tee time alerts"

        except Exception as e:
            logger.error(f"TEE TIME ALERTS: Error: {e}")
            return f"Error: {e}"