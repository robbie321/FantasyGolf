"""Add creator_id to League and remove site_admin_id

Revision ID: 188cd73ae0b8
Revises: ef4ab1f20b9f
Create Date: 2025-09-16 15:13:49.610455

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '188cd73ae0b8'
down_revision = 'ef4ab1f20b9f'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Add the creator_id column and its foreign key, allowing NULLs.
    op.add_column('leagues', sa.Column('creator_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_leagues_creator_id_users', 'leagues', 'users', ['creator_id'], ['id'])

    # Step 2: Populate creator_id from existing data.
    op.execute('UPDATE leagues SET creator_id = site_admin_id WHERE site_admin_id IS NOT NULL')
    op.execute("""
        UPDATE leagues
        SET creator_id = (SELECT user_id FROM clubs WHERE clubs.id = leagues.club_id)
        WHERE club_id IS NOT NULL AND creator_id IS NULL
    """)

    # --- THE NEW, MORE ROBUST FIX ---
    # Step 2.5 (Ultimate Fallback): Assign any remaining orphans to the very first user.
    # This guarantees no creator_id will be left as NULL.
    op.execute("""
        UPDATE leagues
        SET creator_id = (SELECT id FROM users ORDER BY id LIMIT 1)
        WHERE creator_id IS NULL
    """)
    # --- END FIX ---

    # Step 3: Now, enforce the NOT NULL constraint.
    op.alter_column('leagues', 'creator_id',
                    existing_type=sa.Integer(),
                    nullable=False)

    # Step 4: Drop the old column.
    op.drop_constraint('leagues_site_admin_id_fkey', 'leagues', type_='foreignkey')
    op.drop_column('leagues', 'site_admin_id')




def downgrade():
    # To reverse the process, we add back site_admin_id and drop creator_id.
    op.add_column('leagues', sa.Column('site_admin_id', sa.Integer(), autoincrement=False, nullable=True))
    op.create_foreign_key('leagues_site_admin_id_fkey', 'leagues', 'users', ['site_admin_id'], ['id'])

    # This part is tricky as data might be lost, but we do our best.
    # We assume if the creator is a site admin, we populate the old column.
    op.execute("""
        UPDATE leagues
        SET site_admin_id = creator_id
        FROM users
        WHERE leagues.creator_id = users.id AND users.is_site_admin = TRUE
    """)

    op.drop_constraint('fk_leagues_creator_id_users', 'leagues', type_='foreignkey')
    op.drop_column('leagues', 'creator_id')
