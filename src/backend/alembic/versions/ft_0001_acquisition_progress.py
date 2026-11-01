"""Persist account-scoped acquisition checkpoints in the public trade derivative.

Revision ID: ft_0001
Revises: ce_0034
"""
from alembic import op
import sqlalchemy as sa

revision='ft_0001'
down_revision='ce_0034'
branch_labels=None
depends_on=None

def upgrade():
    if 'foreign_trade_acquisition_progress' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table('foreign_trade_acquisition_progress',
        sa.Column('owner_user_id',sa.String(64),primary_key=True),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('payload',sa.JSON(),nullable=False),
        sa.Column('updated_at',sa.String(40),nullable=False))

def downgrade():
    op.drop_table('foreign_trade_acquisition_progress')
