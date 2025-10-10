-- Drop league_templates table and all related indexes
-- Run this to clean up before re-running migration

-- Drop indexes first
DROP INDEX IF EXISTS idx_template_name;
DROP INDEX IF EXISTS idx_template_club;

-- Drop the table
DROP TABLE IF EXISTS league_templates CASCADE;

-- Verify it's gone
SELECT 'league_templates table and indexes dropped successfully!' as message;
