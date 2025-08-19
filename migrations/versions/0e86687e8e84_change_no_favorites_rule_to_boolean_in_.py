"""Change no_favorites_rule to Boolean in League model

Revision ID: 0e86687e8e84
Revises: fd006b156df5
Create Date: 2025-08-18 17:22:45.610034

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0e86687e8e84'
down_revision = 'fd006b156df5'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('leagues', schema=None) as batch_op:
        # Drop the old integer-based default value
        batch_op.alter_column('no_favorites_rule',
                              server_default=None)
        # Alter the column type, using the casting hint
        batch_op.alter_column('no_favorites_rule',
                              existing_type=sa.INTEGER(),
                              type_=sa.Boolean(),
                              existing_nullable=False,
                              postgresql_using='no_favorites_rule::boolean')
        # Create the new boolean-based default value
        batch_op.alter_column('no_favorites_rule',
                              server_default=sa.text('false'))

def downgrade():
    with op.batch_alter_table('leagues', schema=None) as batch_op:
        # Drop the boolean-based default value
        batch_op.alter_column('no_favorites_rule',
                              server_default=None)
        # Alter the column type back to integer
        batch_op.alter_column('no_favorites_rule',
                              existing_type=sa.Boolean(),
                              type_=sa.INTEGER(),
                              existing_nullable=False,
                              postgresql_using='no_favorites_rule::integer')
        # Recreate the integer-based default value
        batch_op.alter_column('no_favorites_rule',
                              server_default=sa.text('0'))

    # ### end Alembic commands ###
