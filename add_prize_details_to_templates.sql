-- Add prize_details column to league_templates table

ALTER TABLE league_templates ADD COLUMN IF NOT EXISTS prize_details TEXT;

-- Display success message
SELECT 'prize_details column added to league_templates table successfully!' as message;
