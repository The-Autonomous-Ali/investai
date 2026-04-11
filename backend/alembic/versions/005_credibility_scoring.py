"""Add credibility scoring columns to signals table.

Revision ID: 005
Revises: 003
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('signals', sa.Column('credibility_score', sa.Float(), nullable=True))
    op.add_column('signals', sa.Column('claim_type', sa.String(), nullable=True))
    op.add_column('signals', sa.Column('source_urls', sa.JSON(), nullable=True))
    op.add_column('signals', sa.Column('corroboration_count', sa.Integer(), server_default='0'))


def downgrade() -> None:
    op.drop_column('signals', 'corroboration_count')
    op.drop_column('signals', 'source_urls')
    op.drop_column('signals', 'claim_type')
    op.drop_column('signals', 'credibility_score')
