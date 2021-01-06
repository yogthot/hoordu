"""added source_id to the subscription unique index

Revision ID: 1986100c0bcc
Revises: 9fc955710ef2
Create Date: 2020-12-28 14:50:21.607780

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1986100c0bcc'
down_revision = '9fc955710ef2'
branch_labels = None
depends_on = None


def upgrade():
    #Index('idx_subscription', 'source_id', 'name', unique=True),
    op.drop_index('ix_subscription_name', table_name='subscription')
    op.create_index('idx_subscription', 'subscription', ['source_id', 'name'], unique=True)


def downgrade():
    op.drop_index('idx_subscription', table_name='subscription')
    op.create_index('ix_subscription_name', 'subscription', ['name'], unique=True)
