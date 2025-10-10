"""
Diagnostic script to check why leagues aren't finalizing
"""
import os
import sys

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fantasy_league_app import create_app, db
from fantasy_league_app.models import League, LeagueEntry, PlayerScore, Player
from datetime import datetime

app = create_app()

with app.app_context():
    print("=" * 80)
    print("LEAGUE FINALIZATION DIAGNOSTIC")
    print("=" * 80)

    now = datetime.utcnow()
    print(f"\nCurrent UTC Time: {now}")
    print(f"Current UTC Date: {now.date()}")

    # Find leagues that should be finalized
    leagues_to_finalize = League.query.filter(
        League.end_date <= now,
        League.is_finalized == False
    ).all()

    print(f"\n{'='*80}")
    print(f"Found {len(leagues_to_finalize)} leagues to finalize:")
    print(f"{'='*80}\n")

    for league in leagues_to_finalize:
        print(f"\n📋 League ID {league.id}: {league.name}")
        print(f"   End Date: {league.end_date}")
        print(f"   End Date <= Now: {league.end_date <= now}")
        print(f"   Is Finalized: {league.is_finalized}")
        print(f"   Number of Entries: {len(league.entries)}")

        if not league.entries:
            print(f"   ⚠️  WARNING: No entries in this league!")
            continue

        # Check for historical scores
        historical_scores_count = PlayerScore.query.filter_by(league_id=league.id).count()
        print(f"   Historical Scores Archived: {historical_scores_count}")

        # Check each entry
        print(f"\n   Entries:")
        for i, entry in enumerate(league.entries, 1):
            print(f"      Entry {i} (ID: {entry.id}):")
            print(f"         User ID: {entry.user_id}")
            print(f"         Player 1 ID: {entry.player1_id}")
            print(f"         Player 2 ID: {entry.player2_id}")
            print(f"         Player 3 ID: {entry.player3_id}")

            # Check if players exist
            if entry.player1_id:
                p1 = Player.query.get(entry.player1_id)
                print(f"         Player 1: {p1.name if p1 else 'NOT FOUND'} - Current Score: {p1.current_score if p1 else 'N/A'}")

            if entry.player2_id:
                p2 = Player.query.get(entry.player2_id)
                print(f"         Player 2: {p2.name if p2 else 'NOT FOUND'} - Current Score: {p2.current_score if p2 else 'N/A'}")

            if entry.player3_id:
                p3 = Player.query.get(entry.player3_id)
                print(f"         Player 3: {p3.name if p3 else 'NOT FOUND'} - Current Score: {p3.current_score if p3 else 'N/A'}")

            # Try to get total_score
            try:
                total = entry.total_score
                print(f"         Total Score: {total}")
            except Exception as e:
                print(f"         Total Score: ERROR - {e}")

            print(f"         Tiebreaker Answer: {entry.tie_breaker_answer}")

        # Check tiebreaker
        print(f"\n   Tiebreaker Actual Answer: {league.tie_breaker_actual_answer}")
        if league.tie_breaker_actual_answer is None:
            print(f"   ⚠️  WARNING: No tiebreaker answer set!")

        print(f"\n   {'='*70}")

    print(f"\n{'='*80}")
    print("END OF DIAGNOSTIC")
    print(f"{'='*80}\n")
