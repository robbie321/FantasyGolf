-- Update league_templates table to new simplified structure
-- This script will drop old columns and add the new rules column

-- Drop old columns that are no longer needed
ALTER TABLE league_templates DROP COLUMN IF EXISTS tour;
ALTER TABLE league_templates DROP COLUMN IF EXISTS bucket_a_picks;
ALTER TABLE league_templates DROP COLUMN IF EXISTS bucket_b_picks;
ALTER TABLE league_templates DROP COLUMN IF EXISTS bucket_c_picks;
ALTER TABLE league_templates DROP COLUMN IF EXISTS bucket_d_picks;
ALTER TABLE league_templates DROP COLUMN IF EXISTS bucket_e_picks;
ALTER TABLE league_templates DROP COLUMN IF EXISTS is_public;
ALTER TABLE league_templates DROP COLUMN IF EXISTS require_payment;
ALTER TABLE league_templates DROP COLUMN IF EXISTS tiebreaker_question;

-- Add new rules column for rich text HTML
ALTER TABLE league_templates ADD COLUMN IF NOT EXISTS rules TEXT;

-- Display success message
SELECT 'league_templates table updated successfully!' as message;
