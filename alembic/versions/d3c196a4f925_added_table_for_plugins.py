"""added table for plugins

Revision ID: d3c196a4f925
Revises: 975a199df79a
Create Date: 2022-02-13 10:47:44.764393

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = 'd3c196a4f925'
down_revision = '975a199df79a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('plugin',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255, collation='NOCASE'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('config', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['source.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_plugin_name', 'plugin', ['name'], unique=True)
    
    bind = op.get_bind()
    bind.execute(text('insert into plugin(id, source_id, name, version, config) select id, id, name, version, config from source'))
    
    op.drop_column('source', 'config')
    op.drop_column('source', 'version')
    op.alter_column('source', 'hoordu_config', new_column_name='config')
    
    op.add_column('subscription', sa.Column('plugin_id', sa.INTEGER(), nullable=True))
    bind.execute(text('update subscription set plugin_id = source_id'))
    
    op.create_foreign_key('subscription_plugin_id_fkey', 'subscription', 'plugin', ['plugin_id'], ['id'], ondelete='CASCADE')
    
    row = list(bind.execute(text('select max(id) from plugin')))
    maxid = 1 if len(row) == 0 else row[0][0]
    bind.execute(text(f'alter sequence plugin_id_seq restart with {maxid + 1}'))


def downgrade():
    op.drop_column('subscription', 'plugin_id')
    
    op.alter_column('source', 'config', new_column_name='hoordu_config')
    
    op.add_column('source', 'version')
    op.add_column('source', 'config')
    
    bind = op.get_bind()
    res = bind.execute(text('select name, config, version from plugin'))
    
    for name, config, version in res:
        bind.execute(
            text('update source set config = :config, version = :version where name = :name'),
            config=config, version=version, name=name
        )
    
    
    op.drop_table('plugin')
