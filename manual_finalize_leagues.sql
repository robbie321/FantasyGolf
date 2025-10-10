-- Manual League Finalization Script
-- Run this if the automatic finalization isn't working

-- First, let's check what we're dealing with
SELECT
    id,
    name,
    end_date,
    is_finalized,
    tie_breaker_actual_answer,
    (SELECT COUNT(*) FROM league_entries WHERE league_id = leagues.id) as entry_count
FROM leagues
WHERE end_date <= NOW()
  AND is_finalized = FALSE
ORDER BY end_date DESC;

-- Check if entries have scores
SELECT
    le.id as entry_id,
    le.league_id,
    le.user_id,
    le.player1_id,
    le.player2_id,
    le.player3_id,
    le.tie_breaker_answer,
    p1.current_score as player1_score,
    p2.current_score as player2_score,
    p3.current_score as player3_score,
    (COALESCE(p1.current_score, 0) + COALESCE(p2.current_score, 0) + COALESCE(p3.current_score, 0)) as total_score
FROM league_entries le
LEFT JOIN players p1 ON le.player1_id = p1.id
LEFT JOIN players p2 ON le.player2_id = p2.id
LEFT JOIN players p3 ON le.player3_id = p3.id
WHERE le.league_id IN (39, 43, 44, 45)
ORDER BY le.league_id, total_score;

-- Check if PlayerScores have been archived
SELECT
    league_id,
    COUNT(*) as scores_archived
FROM player_scores
WHERE league_id IN (39, 43, 44, 45)
GROUP BY league_id;

-- IMPORTANT: Before running finalization, you need to:
-- 1. Archive player scores (if not done)
-- 2. Set tiebreaker actual answer (if there's a tie)

-- To set tiebreaker answer for a league (example for league 39):
-- UPDATE leagues SET tie_breaker_actual_answer = 72 WHERE id = 39;

-- To manually archive player scores for a league (run for each league that needs it):
/*
INSERT INTO player_scores (player_id, league_id, score)
SELECT DISTINCT
    p.id,
    39 as league_id,  -- Change this league ID for each league
    p.current_score
FROM players p
WHERE p.id IN (
    SELECT player1_id FROM league_entries WHERE league_id = 39
    UNION
    SELECT player2_id FROM league_entries WHERE league_id = 39
    UNION
    SELECT player3_id FROM league_entries WHERE league_id = 39
);
*/

-- After scores are archived and tiebreaker is set, you can manually finalize:
/*
-- For League 39 (example)
UPDATE leagues
SET
    is_finalized = TRUE,
    winner_id = (
        SELECT user_id
        FROM (
            SELECT
                le.user_id,
                (
                    COALESCE((SELECT score FROM player_scores WHERE player_id = le.player1_id AND league_id = 39), 0) +
                    COALESCE((SELECT score FROM player_scores WHERE player_id = le.player2_id AND league_id = 39), 0) +
                    COALESCE((SELECT score FROM player_scores WHERE player_id = le.player3_id AND league_id = 39), 0)
                ) as total_score
            FROM league_entries le
            WHERE le.league_id = 39
            ORDER BY total_score ASC,
                     ABS(le.tie_breaker_answer - leagues.tie_breaker_actual_answer) ASC
            LIMIT 1
        ) as winner
    )
WHERE id = 39;
*/
