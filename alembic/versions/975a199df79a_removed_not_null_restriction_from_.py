"""removed not null restriction from remote_post original_id

Revision ID: 975a199df79a
Revises: 1e4613f33072
Create Date: 2021-06-25 01:46:41.271979

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '975a199df79a'
down_revision = '1e4613f33072'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('remote_post', 'original_id', nullable=True)


def downgrade():
    op.alter_column('remote_post', 'original_id', nullable=False)
