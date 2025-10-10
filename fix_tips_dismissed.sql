-- Fix tips_dismissed NULL values in the database
-- Run this SQL directly in your PostgreSQL database to immediately fix the issue

-- Update all NULL or invalid tips_dismissed values to empty JSON arrays
UPDATE users
SET tips_dismissed = '[]'::json
WHERE tips_dismissed IS NULL
   OR tips_dismissed::text = 'null'
   OR tips_dismissed::text = '';

-- Verify the fix
SELECT id, email, tips_dismissed
FROM users
WHERE tips_dismissed IS NULL OR tips_dismissed::text = 'null';

-- This should return no rows if the fix was successful
