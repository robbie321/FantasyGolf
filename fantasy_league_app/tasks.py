from datetime import datetime, timedelta
from collections import defaultdict
import requests
from sqlalchemy import func

from .models import League, Player
from . import db, mail, socketio # Make sure mail is imported if you use it in other tasks
from flask_mail import Message

from .data_golf_client import DataGolfClient

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
