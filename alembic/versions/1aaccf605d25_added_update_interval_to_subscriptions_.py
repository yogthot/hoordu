"""Added update_interval to subscriptions for finer control.

Revision ID: 1aaccf605d25
Revises: b951270a8659
Create Date: 2026-02-27 23:22:01.387668

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1aaccf605d25'
down_revision = 'b951270a8659'
branch_labels = None
depends_on = None


def upgrade():
    #update_interval: Mapped[Optional[timedelta]] = mapped_column(Interval)
    op.add_column('subscription', sa.Column('update_interval', sa.Interval(), nullable=True))



def downgrade():
    op.drop_column('subscription', 'update_interval')
