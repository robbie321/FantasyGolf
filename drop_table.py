"""Script to drop league_templates table and indexes"""
from fantasy_league_app import create_app
from fantasy_league_app.extensions import db

app = create_app()

with app.app_context():
    try:
        # Drop indexes
        db.session.execute(db.text('DROP INDEX IF EXISTS idx_template_name'))
        db.session.execute(db.text('DROP INDEX IF EXISTS idx_template_club'))

        # Drop table
        db.session.execute(db.text('DROP TABLE IF EXISTS league_templates CASCADE'))

        db.session.commit()
        print('✅ league_templates table and indexes dropped successfully!')
    except Exception as e:
        db.session.rollback()
        print(f'❌ Error: {e}')
