"""Changed some ondelete rules to make the schema safer.

Revision ID: 192295585a7e
Revises: 660287dad205
Create Date: 2024-09-19 21:33:26.608912

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '192295585a7e'
down_revision = '660287dad205'
branch_labels = None
depends_on = None


def upgrade():
    #Subscription.source_id CASCADE DELETE -> None     | subscription_service_id_fkey
    #Subscription.plugin_id CASCADE DELETE -> SET NULL | subscription_plugin_id_fkey
    #RemotePost.source_id CASCADE DELETE -> None       | remote_post_service_id_fkey
    #RemoteTag.source_id CASCADE DELETE -> None        | remote_tag_service_id_fkey
    
    op.drop_constraint(constraint_name='subscription_service_id_fkey', table_name='subscription', type_='foreignkey')
    op.create_foreign_key(
        constraint_name='subscription_source_id_fkey',
        source_table='subscription',
        referent_table='source',
        local_cols=['source_id'],
        remote_cols=['id'])
    
    op.drop_constraint(constraint_name='subscription_plugin_id_fkey', table_name='subscription', type_='foreignkey')
    op.create_foreign_key(
        constraint_name='subscription_plugin_id_fkey',
        source_table='subscription',
        referent_table='plugin',
        local_cols=['plugin_id'],
        remote_cols=['id'],
        ondelete='SET NULL')
    
    op.drop_constraint(constraint_name='remote_post_service_id_fkey', table_name='remote_post', type_='foreignkey')
    op.create_foreign_key(
        constraint_name='remote_post_service_id_fkey',
        source_table='remote_post',
        referent_table='source',
        local_cols=['source_id'],
        remote_cols=['id'])
    
    op.drop_constraint(constraint_name='remote_tag_service_id_fkey', table_name='remote_tag', type_='foreignkey')
    op.create_foreign_key(
        constraint_name='remote_tag_service_id_fkey',
        source_table='remote_tag',
        referent_table='source',
        local_cols=['source_id'],
        remote_cols=['id'])


def downgrade():
    pass
