"""Added remote identifier to file.

Revision ID: a25551a6b096
Revises: 192295585a7e
Create Date: 2024-10-05 21:58:11.757570

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = 'a25551a6b096'
down_revision = '192295585a7e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('file', sa.Column('remote_identifier', sa.Text(), nullable=True))
    
    # move metadata into remote_identifier, unless it starts with "{" (json object)
    bind = op.get_bind()
    bind.execute(text("""
        update file
        set remote_identifier = metadata
        where metadata not like '{%'
        """))
    
    bind.execute(text("""
        update file
        set metadata = NULL
        where metadata not like '{%'
        """))


def downgrade():
    op.drop_column('file', 'remote_identifier')
