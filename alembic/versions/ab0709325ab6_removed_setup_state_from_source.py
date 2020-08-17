"""removed setup_state from source

Revision ID: ab0709325ab6
Revises: 7904395585e7
Create Date: 2020-08-18 22:26:45.842005

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ab0709325ab6'
down_revision = '7904395585e7'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('source', 'setup_state')


def downgrade():
    op.add_column('source', sa.Column('setup_state', sa.INTEGER(), autoincrement=False, nullable=False))
