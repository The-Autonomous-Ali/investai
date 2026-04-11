"""Add root cause chain columns to signals table.

Stores structured root cause, resolution, and assembled causal chain
data so the system can explain WHY events are happening, not just
that they are happening.

Revision ID: 004
Revises: 003
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('signals', sa.Column('root_cause_chain', sa.JSON(), server_default='[]'))
    op.add_column('signals', sa.Column('resolution_chain', sa.JSON(), server_default='[]'))
    op.add_column('signals', sa.Column('full_causal_chain', sa.JSON(), server_default='{}'))


def downgrade() -> None:
    op.drop_column('signals', 'full_causal_chain')
    op.drop_column('signals', 'resolution_chain')
    op.drop_column('signals', 'root_cause_chain')
