"""Add push notification tables

Revision ID: 230fc38d99f8
Revises: c626ddcc7666
Create Date: 2025-09-23 09:48:04.304507

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '230fc38d99f8'
down_revision = 'c626ddcc7666'
branch_labels = None
depends_on = None

def upgrade():
    # Enhance existing push_subscriptions table
    # (Add columns if they don't exist)
    try:
        op.add_column('push_subscriptions', sa.Column('user_agent', sa.String(500), nullable=True))
    except:
        pass  # Column might already exist

    try:
        op.add_column('push_subscriptions', sa.Column('is_active', sa.Boolean(), default=True))
    except:
        pass

    try:
        op.add_column('push_subscriptions', sa.Column('created_at', sa.DateTime(), default=sa.func.now()))
    except:
        pass

    try:
        op.add_column('push_subscriptions', sa.Column('last_used', sa.DateTime(), default=sa.func.now()))
    except:
        pass

    # Create notification_logs table
    op.create_table('notification_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('subscription_id', sa.Integer(), nullable=True),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('data', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=True, default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True, default=sa.func.now()),
        sa.Column('clicked_at', sa.DateTime(), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['subscription_id'], ['push_subscriptions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('idx_notification_user', 'notification_logs', ['user_id'])
    op.create_index('idx_notification_type', 'notification_logs', ['notification_type'])
    op.create_index('idx_notification_status', 'notification_logs', ['status'])
    op.create_index('idx_notification_sent', 'notification_logs', ['sent_at'])

    # Create notification_templates table
    op.create_table('notification_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('title_template', sa.String(255), nullable=False),
        sa.Column('body_template', sa.Text(), nullable=False),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('icon', sa.String(255), nullable=True),
        sa.Column('badge', sa.String(255), nullable=True),
        sa.Column('actions', sa.Text(), nullable=True),
        sa.Column('require_interaction', sa.Boolean(), nullable=True, default=False),
        sa.Column('vibrate_pattern', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create indexes
    op.create_index('idx_template_name', 'notification_templates', ['name'])
    op.create_index('idx_template_type', 'notification_templates', ['notification_type'])

    # Create notification_preferences table
    op.create_table('notification_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('league_updates', sa.Boolean(), nullable=True, default=True),
        sa.Column('score_updates', sa.Boolean(), nullable=True, default=True),
        sa.Column('tournament_start', sa.Boolean(), nullable=True, default=True),
        sa.Column('tournament_end', sa.Boolean(), nullable=True, default=True),
        sa.Column('prize_notifications', sa.Boolean(), nullable=True, default=True),
        sa.Column('marketing', sa.Boolean(), nullable=True, default=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )

    # Create indexes
    op.create_index('idx_pref_user', 'notification_preferences', ['user_id'])


def downgrade():
    op.drop_index('idx_pref_user', table_name='notification_preferences')
    op.drop_table('notification_preferences')

    op.drop_index('idx_template_type', table_name='notification_templates')
    op.drop_index('idx_template_name', table_name='notification_templates')
    op.drop_table('notification_templates')

    op.drop_index('idx_notification_sent', table_name='notification_logs')
    op.drop_index('idx_notification_status', table_name='notification_logs')
    op.drop_index('idx_notification_type', table_name='notification_logs')
    op.drop_index('idx_notification_user', table_name='notification_logs')
    op.drop_table('notification_logs')

    # Remove added columns from push_subscriptions (optional)
    # op.drop_column('push_subscriptions', 'last_used')
    # op.drop_column('push_subscriptions', 'created_at')
    # op.drop_column('push_subscriptions', 'is_active')
    # op.drop_column('push_subscriptions', 'user_agent')