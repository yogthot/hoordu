"""added preferred plugin to source

Revision ID: d4eaa251695b
Revises: d3c196a4f925
Create Date: 2022-02-13 18:34:59.768469

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4eaa251695b'
down_revision = 'd3c196a4f925'
branch_labels = None
depends_on = None


def upgrade():
    #preferred_plugin_id = Column(Integer, ForeignKey('plugin.id', ondelete='SET NULL'), nullable=True)
    op.add_column('source', sa.Column('preferred_plugin_id', sa.Integer(), nullable=True))
    op.create_foreign_key('source_preferred_plugin_id_fkey', 'source', 'plugin', ['preferred_plugin_id'], ['id'])


def downgrade():
    op.drop_column('source', 'preferred_plugin_id')
