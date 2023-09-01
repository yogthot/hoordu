"""added sort index to feed

Revision ID: a4cadea23924
Revises: 207cfb2c165b
Create Date: 2023-07-28 00:32:53.280378

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = 'a4cadea23924'
down_revision = '207cfb2c165b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('feed', sa.Column('sort_index', sa.Numeric(), default=0, nullable=True))
    
    bind = op.get_bind()
    bind.execute(text("""
        update feed
        set sort_index = sort.sort_index
        from (
            select
                f.subscription_id,
                f.remote_post_id,
                CASE WHEN rp.original_id~E'^\\\\d+$' THEN
                    rp.original_id::NUMERIC
                ELSE
                    extract(epoch from rp.post_time)::NUMERIC
                END as sort_index
                from feed f
                join remote_post rp on f.remote_post_id = rp.id) AS sort
        where feed.subscription_id = sort.subscription_id and feed.remote_post_id = sort.remote_post_id
        """))
    
    op.alter_column('feed', 'sort_index', nullable=False)


def downgrade():
    op.drop_column('feed', 'sort_index')
