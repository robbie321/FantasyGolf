"""Fix tips_dismissed NULL values

Revision ID: fix_tips_dismissed
Revises: d224b896cced
Create Date: 2025-10-06 20:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'fix_tips_dismissed'
down_revision = 'd224b896cced'
branch_labels = None
depends_on = None


def upgrade():
    # Update all NULL or invalid tips_dismissed values to empty JSON arrays
    # This handles both NULL values and any potential bad data
    connection = op.get_bind()

    # For PostgreSQL
    connection.execute(
        text("""
            UPDATE users
            SET tips_dismissed = '[]'::json
            WHERE tips_dismissed IS NULL
               OR tips_dismissed::text = 'null'
               OR tips_dismissed::text = ''
        """)
    )


def downgrade():
    # No downgrade needed - we're just fixing data, not changing schema
    pass
