"""added metadata to subscription

Revision ID: 207cfb2c165b
Revises: d4eaa251695b
Create Date: 2022-11-28 21:29:19.781313

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '207cfb2c165b'
down_revision = 'd4eaa251695b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('subscription', sa.Column('metadata', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('subscription', 'metadata')