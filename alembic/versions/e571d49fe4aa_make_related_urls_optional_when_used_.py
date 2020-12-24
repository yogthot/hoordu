"""make related urls optional (when used for posts in the same source)

Revision ID: e571d49fe4aa
Revises: ab0709325ab6
Create Date: 2020-12-18 23:35:18.036992

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e571d49fe4aa'
down_revision = 'ab0709325ab6'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('related', 'url', nullable=True)


def downgrade():
    op.alter_column('related', 'url', nullable=False)
