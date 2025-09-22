# First, rollback the failed migration:
# flask --app fantasy_league_app:create_app db downgrade

# Then, replace the content of your migration file with this:
# File: migrations/versions/e29dcb347773_add_email_verification_fields.py

"""Add email verification fields

Revision ID: e29dcb347773
Revises: c84025fad242
Create Date: 2025-09-22 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e29dcb347773'
down_revision = 'c84025fad242'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Add columns as nullable first
    with op.batch_alter_table('users', schema=None) as batch_op:
        # Add email verification columns as nullable
        batch_op.add_column(sa.Column('email_verified', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('email_verification_token', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('email_verification_sent_at', sa.DateTime(), nullable=True))

    # Step 2: Create unique constraint on email_verification_token (nullable)
    op.create_unique_constraint(
        'uq_users_email_verification_token',
        'users',
        ['email_verification_token']
    )

    # Step 3: Update existing users - mark them as verified since they're already in the system
    op.execute(
        """
        UPDATE users
        SET email_verified = true
        WHERE email_verified IS NULL
        """
    )

    # Step 4: Now make email_verified NOT NULL since all rows have values
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email_verified', nullable=False)


def downgrade():
    # Remove the unique constraint
    op.drop_constraint('uq_users_email_verification_token', 'users', type_='unique')

    # Remove the columns
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('email_verification_sent_at')
        batch_op.drop_column('email_verification_token')
        batch_op.drop_column('email_verified')