# Replace the content of your migration file with this safer version:
# File: migrations/versions/c626ddcc7666_add_profile_enhancement_fields_and_user_.py

"""Add profile enhancement fields and user activity tracking

Revision ID: c626ddcc7666
Revises: e29dcb347773
Create Date: 2025-09-22 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c626ddcc7666'
down_revision = 'e29dcb347773'
branch_labels = None
depends_on = None

def column_exists(table_name, column_name):
    """Check if a column exists in a table"""
    connection = op.get_bind()
    result = connection.execute(
        sa.text("""
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_name = :table_name
        AND column_name = :column_name
        """),
        {"table_name": table_name, "column_name": column_name}
    )
    return result.scalar() > 0

def upgrade():
    # Add new fields to users table
    with op.batch_alter_table('users', schema=None) as batch_op:
        # Only add columns that don't exist
        if not column_exists('users', 'created_at'):
            batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        if not column_exists('users', 'last_active'):
            batch_op.add_column(sa.Column('last_active', sa.DateTime(), nullable=True))
        if not column_exists('users', 'profile_views'):
            batch_op.add_column(sa.Column('profile_views', sa.Integer(), nullable=True))
        if not column_exists('users', 'achievement_data'):
            batch_op.add_column(sa.Column('achievement_data', sa.Text(), nullable=True))
        if not column_exists('users', 'email_rank_changes'):
            batch_op.add_column(sa.Column('email_rank_changes', sa.Boolean(), nullable=True))
        if not column_exists('users', 'email_league_updates'):
            batch_op.add_column(sa.Column('email_league_updates', sa.Boolean(), nullable=True))
        if not column_exists('users', 'email_tournament_results'):
            batch_op.add_column(sa.Column('email_tournament_results', sa.Boolean(), nullable=True))
        if not column_exists('users', 'email_achievements'):
            batch_op.add_column(sa.Column('email_achievements', sa.Boolean(), nullable=True))

    # Set default values for existing users
    op.execute("""
        UPDATE users
        SET
            created_at = COALESCE(created_at, NOW()),
            last_active = COALESCE(last_active, NOW()),
            profile_views = COALESCE(profile_views, 0),
            email_rank_changes = COALESCE(email_rank_changes, true),
            email_league_updates = COALESCE(email_league_updates, true),
            email_tournament_results = COALESCE(email_tournament_results, true),
            email_achievements = COALESCE(email_achievements, true)
        WHERE
            created_at IS NULL OR
            last_active IS NULL OR
            profile_views IS NULL OR
            email_rank_changes IS NULL OR
            email_league_updates IS NULL OR
            email_tournament_results IS NULL OR
            email_achievements IS NULL
    """)

    # Make fields non-nullable after setting defaults
    with op.batch_alter_table('users', schema=None) as batch_op:
        if column_exists('users', 'created_at'):
            batch_op.alter_column('created_at', nullable=False)
        if column_exists('users', 'last_active'):
            batch_op.alter_column('last_active', nullable=False)
        if column_exists('users', 'profile_views'):
            batch_op.alter_column('profile_views', nullable=False)
        if column_exists('users', 'email_rank_changes'):
            batch_op.alter_column('email_rank_changes', nullable=False)
        if column_exists('users', 'email_league_updates'):
            batch_op.alter_column('email_league_updates', nullable=False)
        if column_exists('users', 'email_tournament_results'):
            batch_op.alter_column('email_tournament_results', nullable=False)
        if column_exists('users', 'email_achievements'):
            batch_op.alter_column('email_achievements', nullable=False)

    # Add new fields to league_entries table
    with op.batch_alter_table('league_entries', schema=None) as batch_op:
        # Only add columns that don't exist
        if not column_exists('league_entries', 'created_at'):
            batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        if not column_exists('league_entries', 'final_rank'):
            batch_op.add_column(sa.Column('final_rank', sa.Integer(), nullable=True))
        if not column_exists('league_entries', 'previous_rank'):
            batch_op.add_column(sa.Column('previous_rank', sa.Integer(), nullable=True))
        if not column_exists('league_entries', 'rank_change_count'):
            batch_op.add_column(sa.Column('rank_change_count', sa.Integer(), nullable=True))

    # Set default values for existing league entries
    op.execute("""
        UPDATE league_entries
        SET
            created_at = COALESCE(created_at, NOW()),
            rank_change_count = COALESCE(rank_change_count, 0)
        WHERE created_at IS NULL OR rank_change_count IS NULL
    """)

    # Make non-nullable fields non-nullable
    with op.batch_alter_table('league_entries', schema=None) as batch_op:
        if column_exists('league_entries', 'created_at'):
            batch_op.alter_column('created_at', nullable=False)
        if column_exists('league_entries', 'rank_change_count'):
            batch_op.alter_column('rank_change_count', nullable=False)

    # Create user_activities table only if it doesn't exist
    connection = op.get_bind()
    table_exists = connection.execute(
        sa.text("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = 'user_activities'
        """)
    ).scalar() > 0

    if not table_exists:
        op.create_table('user_activities',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('activity_type', sa.String(length=50), nullable=False),
            sa.Column('description', sa.String(length=200), nullable=False),
            sa.Column('league_id', sa.Integer(), nullable=True),
            sa.Column('extra_data', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['league_id'], ['leagues.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

        # Create indexes for performance
        op.create_index('ix_user_activities_user_id', 'user_activities', ['user_id'])
        op.create_index('ix_user_activities_created_at', 'user_activities', ['created_at'])
        op.create_index('ix_user_activities_activity_type', 'user_activities', ['activity_type'])

def downgrade():
    # Check if indexes exist before dropping
    connection = op.get_bind()

    index_exists = lambda idx_name: connection.execute(
        sa.text("""
        SELECT COUNT(*)
        FROM pg_indexes
        WHERE indexname = :idx_name
        """),
        {"idx_name": idx_name}
    ).scalar() > 0

    # Drop indexes if they exist
    if index_exists('ix_user_activities_activity_type'):
        op.drop_index('ix_user_activities_activity_type', table_name='user_activities')
    if index_exists('ix_user_activities_created_at'):
        op.drop_index('ix_user_activities_created_at', table_name='user_activities')
    if index_exists('ix_user_activities_user_id'):
        op.drop_index('ix_user_activities_user_id', table_name='user_activities')

    # Drop user_activities table if it exists
    table_exists = connection.execute(
        sa.text("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = 'user_activities'
        """)
    ).scalar() > 0

    if table_exists:
        op.drop_table('user_activities')

    # Remove new fields from league_entries
    with op.batch_alter_table('league_entries', schema=None) as batch_op:
        if column_exists('league_entries', 'rank_change_count'):
            batch_op.drop_column('rank_change_count')
        if column_exists('league_entries', 'previous_rank'):
            batch_op.drop_column('previous_rank')
        if column_exists('league_entries', 'final_rank'):
            batch_op.drop_column('final_rank')
        # Note: Don't drop created_at if it existed before this migration

    # Remove new fields from users
    with op.batch_alter_table('users', schema=None) as batch_op:
        if column_exists('users', 'email_achievements'):
            batch_op.drop_column('email_achievements')
        if column_exists('users', 'email_tournament_results'):
            batch_op.drop_column('email_tournament_results')
        if column_exists('users', 'email_league_updates'):
            batch_op.drop_column('email_league_updates')
        if column_exists('users', 'email_rank_changes'):
            batch_op.drop_column('email_rank_changes')
        if column_exists('users', 'achievement_data'):
            batch_op.drop_column('achievement_data')
        if column_exists('users', 'profile_views'):
            batch_op.drop_column('profile_views')
        if column_exists('users', 'last_active'):
            batch_op.drop_column('last_active')
        # Note: Don't drop created_at if it existed before this migration