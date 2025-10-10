# League Finalization Fix

## Problem Identified

Leagues weren't finalizing because of a critical issue with how scores were being calculated:

### Root Cause:

1. **The `total_score` property** on `LeagueEntry` was reading from `Player.current_score`
2. **Player scores get reset weekly** by the `reset_player_scores` task
3. **For old tournaments** (ended weeks ago), `current_score` is 0 or None
4. **The finalization task** couldn't find winners because all scores were 0/None

### The Bug:

```python
# OLD CODE (BROKEN)
@property
def total_score(self):
    scores = [self.player1.current_score, self.player2.current_score, self.player3.current_score]
    valid_scores = [score for score in scores if score is not None]
    return sum(valid_scores) if valid_scores else None
```

This worked fine for **active** tournaments, but failed for **ended** tournaments where scores had been reset.

---

## Solution Implemented

### Fix 1: Updated `total_score` Property ([models.py:738-767](fantasy_league_app/models.py#L738))

**New logic:**
- For **finalized leagues**: Read from `PlayerScore` table (archived scores)
- For **active leagues**: Read from `Player.current_score` (live scores)

```python
@property
def total_score(self):
    """
    Calculate total score dynamically.
    For finalized leagues, use archived PlayerScore.
    For active leagues, use current_score from Player.
    """
    from fantasy_league_app.models import PlayerScore

    # Check if this league is finalized
    if self.league and self.league.is_finalized:
        # Use archived scores from PlayerScore table
        total = 0
        player_ids = [self.player1_id, self.player2_id, self.player3_id]

        for player_id in player_ids:
            if player_id:
                archived_score = PlayerScore.query.filter_by(
                    player_id=player_id,
                    league_id=self.league_id
                ).first()
                if archived_score:
                    total += archived_score.score or 0

        return total if total > 0 else None
    else:
        # Use current scores for active leagues
        scores = [self.player1.current_score, self.player2.current_score, self.player3.current_score]
        valid_scores = [score for score in scores if score is not None]
        return sum(valid_scores) if valid_scores else None
```

### Fix 2: Updated Finalization Task ([tasks.py:1226-1243](fantasy_league_app/tasks.py#L1226))

The finalization task now:
1. Manually calculates scores from `historical_scores` dict
2. Doesn't rely on `entry.total_score` property (which wouldn't work yet)
3. Checks for zero scores and skips leagues with no valid data

```python
# Calculate total scores from historical_scores
entry_scores = {}
for entry in entries:
    total = 0
    for player_id in [entry.player1_id, entry.player2_id, entry.player3_id]:
        if player_id and player_id in historical_scores:
            total += historical_scores[player_id]
    entry_scores[entry.id] = total

# Check if we have any valid scores
if not entry_scores or all(score == 0 for score in entry_scores.values()):
    logger.warning(f"FINALIZE: No valid scores for league {league.id}")
    continue

# Determine winners
min_score = min(entry_scores.values())
top_entries = [entry for entry in entries if entry_scores[entry.id] == min_score]
```

---

## How to Apply the Fix

### Step 1: Deploy the Code Changes

```bash
# Commit the changes
git add fantasy_league_app/models.py fantasy_league_app/tasks.py
git commit -m "Fix league finalization - use archived scores for ended leagues"

# Push to Heroku
git push heroku main
```

### Step 2: Restart Celery Workers

```bash
# Restart workers to load new code
heroku ps:restart worker
heroku ps:restart beat
```

### Step 3: Run Manual Finalization

From admin dashboard:
1. Click **"Finalize Finished Leagues"** button
2. Wait 30 seconds
3. Refresh page
4. Leagues should now be finalized!

Or run via Heroku CLI:
```bash
heroku run flask --app fantasy_league_app:create_app shell
>>> from fantasy_league_app.tasks import finalize_finished_leagues
>>> finalize_finished_leagues.delay()
>>> exit()
```

---

## Testing the Fix

### Test 1: Check Archived Scores Exist

Run this SQL to verify scores were archived:

```sql
SELECT
    league_id,
    COUNT(*) as scores_archived
FROM player_scores
WHERE league_id IN (39, 43, 44, 45)
GROUP BY league_id;
```

**Expected:** You should see scores for each league.

**If NO scores:** The finalization task will archive them automatically when it runs.

### Test 2: Manually Check One League

```sql
-- Check league 39
SELECT
    le.id as entry_id,
    u.full_name,
    p1.name as player1,
    p2.name as player2,
    p3.name as player3,
    COALESCE(ps1.score, 0) + COALESCE(ps2.score, 0) + COALESCE(ps3.score, 0) as total_score
FROM league_entries le
JOIN users u ON le.user_id = u.id
LEFT JOIN players p1 ON le.player1_id = p1.id
LEFT JOIN players p2 ON le.player2_id = p2.id
LEFT JOIN players p3 ON le.player3_id = p3.id
LEFT JOIN player_scores ps1 ON ps1.player_id = le.player1_id AND ps1.league_id = 39
LEFT JOIN player_scores ps2 ON ps2.player_id = le.player2_id AND ps2.league_id = 39
LEFT JOIN player_scores ps3 ON ps3.player_id = le.player3_id AND ps3.league_id = 39
WHERE le.league_id = 39
ORDER BY total_score ASC;
```

This shows who should win league 39.

### Test 3: Check After Finalization

After running finalization:

```sql
SELECT
    id,
    name,
    is_finalized,
    winner_id,
    (SELECT full_name FROM users WHERE id = leagues.winner_id) as winner_name
FROM leagues
WHERE id IN (39, 43, 44, 45);
```

**Expected:** All should have `is_finalized = TRUE` and a `winner_id`.

---

## Troubleshooting

### Issue: "No historical scores" warning

**Cause:** Scores weren't archived before finalization.

**Solution:** The task will automatically archive current scores. But if players' `current_score` has been reset to 0, you'll need to manually set scores.

**Manual archive (if needed):**

```sql
-- For league 39 (example)
-- You need to know what the scores WERE when the tournament ended

INSERT INTO player_scores (player_id, league_id, score)
VALUES
    (123, 39, -5),  -- Replace with actual player_id and score
    (124, 39, -3),
    (125, 39, -2);
    -- etc for all players
```

### Issue: League finalizes but wrong winner

**Cause:** Tiebreaker answer not set or incorrect.

**Solution:** Set the tiebreaker actual answer:

```sql
UPDATE leagues
SET tie_breaker_actual_answer = 72  -- Replace with actual answer
WHERE id = 39;
```

Then re-run finalization.

### Issue: Finalization task times out

**Cause:** Too many leagues to process at once.

**Solution:** Finalize leagues one at a time:

```python
# In Flask shell
from fantasy_league_app.models import League
from fantasy_league_app import db

league = League.query.get(39)
# ... manual finalization logic here
```

---

## Prevention for Future

### Ensure Scores Are Archived Before Reset

The weekly `reset_player_scores` task should check for unfinalized leagues first:

```python
# In reset_player_scores task (tasks.py)
# Before resetting scores, finalize any ended leagues
finalize_finished_leagues.delay()

# Wait a bit
time.sleep(60)

# Then reset scores
```

This ensures leagues are finalized before their scores disappear.

---

## Summary

✅ **Fixed:** `total_score` property now uses archived scores for finalized leagues
✅ **Fixed:** Finalization task calculates scores from `historical_scores` dict
✅ **Fixed:** Added validation to skip leagues with no valid scores
✅ **Ready:** Just deploy and click "Finalize Finished Leagues"

Your 4 leagues (39, 43, 44, 45) should now finalize successfully! 🎉
