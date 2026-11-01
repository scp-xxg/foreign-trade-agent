"""Versioned private lexicons for post-generation risk prompts."""
from alembic import op
import sqlalchemy as sa
revision='ft_0002'
down_revision='ft_0001'
branch_labels=None
depends_on=None

def upgrade():
    if 'foreign_trade_lexicons' not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table('foreign_trade_lexicons',sa.Column('lexicon_id',sa.String(64),primary_key=True),sa.Column('owner_user_id',sa.String(64),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),sa.Column('source_sha256',sa.String(64),nullable=False),sa.Column('payload',sa.JSON(),nullable=False),sa.Column('created_at',sa.String(40),nullable=False))
        op.create_index('ix_trade_lexicon_owner_active','foreign_trade_lexicons',['owner_user_id','active'])

def downgrade():
    op.drop_table('foreign_trade_lexicons')
