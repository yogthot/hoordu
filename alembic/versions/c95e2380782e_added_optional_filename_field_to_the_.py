"""added optional filename field to the file table to store the original filename if needed

Revision ID: c95e2380782e
Revises: e571d49fe4aa
Create Date: 2020-12-19 10:04:29.286236

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c95e2380782e'
down_revision = 'e571d49fe4aa'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('file', sa.Column('filename', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('file', 'filename')
