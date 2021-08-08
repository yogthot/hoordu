"""added repr to subscription

Revision ID: 1e4613f33072
Revises: 1986100c0bcc
Create Date: 2021-06-14 15:52:42.484286

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1e4613f33072'
down_revision = '1986100c0bcc'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('subscription', sa.Column('repr', sa.Text(), nullable=True))
    op.create_index('idx_subscription_repr', 'subscription', ['source_id', 'repr'], unique=True)


def downgrade():
    op.drop_index('idx_subscription_repr', table_name='subscription')
    op.drop_column('subscription', 'repr')
