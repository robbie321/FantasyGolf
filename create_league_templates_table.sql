-- Create league_templates table
CREATE TABLE IF NOT EXISTS league_templates (
    id SERIAL PRIMARY KEY,
    club_id INTEGER NOT NULL REFERENCES clubs(id),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    tour VARCHAR(20) NOT NULL DEFAULT 'PGA',
    entry_fee FLOAT NOT NULL DEFAULT 10.0,
    max_entries INTEGER,
    bucket_a_picks INTEGER NOT NULL DEFAULT 2,
    bucket_b_picks INTEGER NOT NULL DEFAULT 2,
    bucket_c_picks INTEGER NOT NULL DEFAULT 2,
    bucket_d_picks INTEGER NOT NULL DEFAULT 2,
    bucket_e_picks INTEGER NOT NULL DEFAULT 2,
    is_public BOOLEAN DEFAULT FALSE,
    require_payment BOOLEAN DEFAULT TRUE,
    tiebreaker_question VARCHAR(500),
    payout_structure JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    times_used INTEGER DEFAULT 0
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_template_club ON league_templates(club_id);
CREATE INDEX IF NOT EXISTS idx_template_name ON league_templates(name);

-- Display success message
SELECT 'league_templates table created successfully!' as message;
