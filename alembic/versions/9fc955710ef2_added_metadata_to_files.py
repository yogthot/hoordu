"""added metadata to files

Revision ID: 9fc955710ef2
Revises: c95e2380782e
Create Date: 2020-12-26 19:09:00.780640

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9fc955710ef2'
down_revision = 'c95e2380782e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('file', sa.Column('metadata', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('file', 'metadata')