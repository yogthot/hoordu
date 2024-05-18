"""Converted all datetimes to include timezones.

Revision ID: 660287dad205
Revises: a4cadea23924
Create Date: 2024-05-17 21:45:51.028079

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '660287dad205'
down_revision = 'a4cadea23924'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('tag', 'created_time', type_=sa.DateTime(timezone=True))
    op.alter_column('tag', 'updated_time', type_=sa.DateTime(timezone=True))
    
    op.alter_column('post', 'post_time', type_=sa.DateTime(timezone=True))
    op.alter_column('post', 'created_time', type_=sa.DateTime(timezone=True))
    op.alter_column('post', 'updated_time', type_=sa.DateTime(timezone=True))
    
    op.alter_column('source', 'created_time', type_=sa.DateTime(timezone=True))
    op.alter_column('source', 'updated_time', type_=sa.DateTime(timezone=True))
    
    op.alter_column('remote_tag', 'created_time', type_=sa.DateTime(timezone=True))
    op.alter_column('remote_tag', 'updated_time', type_=sa.DateTime(timezone=True))
    
    op.alter_column('remote_post', 'post_time', type_=sa.DateTime(timezone=True))
    op.alter_column('remote_post', 'created_time', type_=sa.DateTime(timezone=True))
    op.alter_column('remote_post', 'updated_time', type_=sa.DateTime(timezone=True))
    
    op.alter_column('file', 'created_time', type_=sa.DateTime(timezone=True))
    op.alter_column('file', 'updated_time', type_=sa.DateTime(timezone=True))
    
    op.alter_column('subscription', 'created_time', type_=sa.DateTime(timezone=True))
    op.alter_column('subscription', 'updated_time', type_=sa.DateTime(timezone=True))
    
    op.alter_column('tag_translation', 'created_time', type_=sa.DateTime(timezone=True))
    op.alter_column('tag_translation', 'updated_time', type_=sa.DateTime(timezone=True))


def downgrade():
    op.alter_column('tag', 'created_time', type_=sa.DateTime(timezone=False))
    op.alter_column('tag', 'updated_time', type_=sa.DateTime(timezone=False))
    
    op.alter_column('post', 'post_time', type_=sa.DateTime(timezone=False))
    op.alter_column('post', 'created_time', type_=sa.DateTime(timezone=False))
    op.alter_column('post', 'updated_time', type_=sa.DateTime(timezone=False))
    
    op.alter_column('source', 'created_time', type_=sa.DateTime(timezone=False))
    op.alter_column('source', 'updated_time', type_=sa.DateTime(timezone=False))
    
    op.alter_column('remote_tag', 'created_time', type_=sa.DateTime(timezone=False))
    op.alter_column('remote_tag', 'updated_time', type_=sa.DateTime(timezone=False))
    
    op.alter_column('remote_post', 'post_time', type_=sa.DateTime(timezone=False))
    op.alter_column('remote_post', 'created_time', type_=sa.DateTime(timezone=False))
    op.alter_column('remote_post', 'updated_time', type_=sa.DateTime(timezone=False))
    
    op.alter_column('file', 'created_time', type_=sa.DateTime(timezone=False))
    op.alter_column('file', 'updated_time', type_=sa.DateTime(timezone=False))
    
    op.alter_column('subscription', 'created_time', type_=sa.DateTime(timezone=False))
    op.alter_column('subscription', 'updated_time', type_=sa.DateTime(timezone=False))
    
    op.alter_column('tag_translation', 'created_time', type_=sa.DateTime(timezone=False))
    op.alter_column('tag_translation', 'updated_time', type_=sa.DateTime(timezone=False))
