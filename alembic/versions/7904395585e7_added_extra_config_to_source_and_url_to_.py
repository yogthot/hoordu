"""added extra config to source and url to remote_post

Revision ID: 7904395585e7
Revises: 71a551a4c732
Create Date: 2020-08-09 18:40:19.622842

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7904395585e7'
down_revision = '71a551a4c732'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('remote_post', sa.Column('url', sa.Text(), nullable=True))
    op.add_column('source', sa.Column('hoordu_config', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('source', 'hoordu_config')
    op.drop_column('remote_post', 'url')
