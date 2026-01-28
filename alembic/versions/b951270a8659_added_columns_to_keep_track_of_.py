"""Added columns to keep track of subscription scheduling.

Revision ID: b951270a8659
Revises: a25551a6b096
Create Date: 2026-01-03 16:08:05.439004

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b951270a8659'
down_revision = 'a25551a6b096'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('source', sa.Column('update_interval', sa.Interval(), nullable=True))
    op.add_column('subscription', sa.Column('last_feed_update_time', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('subscription', 'last_feed_update_time')
    op.drop_column('source', 'update_interval')
