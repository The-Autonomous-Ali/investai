"""Add advice_signal_links table for signal monitoring.

Tracks which signals drove each advice record and whether those signals
have since changed.  The signal_monitor worker checks this table
periodically and creates UserAlerts when thesis-relevant signals shift.

Revision ID: 003
Revises: 002
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'advice_signal_links',

        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('advice_id', sa.String(), sa.ForeignKey('advice_records.id'), nullable=False),
        sa.Column('signal_id', sa.String(), sa.ForeignKey('signals.id'), nullable=True),

        # Snapshot at advice time
        sa.Column('signal_title', sa.String(), nullable=False),
        sa.Column('signal_type', sa.String(), nullable=True),
        sa.Column('importance_at_advice', sa.Float(), nullable=True),
        sa.Column('stage_at_advice', sa.String(), nullable=True),
        sa.Column('sectors_affected', sa.JSON(), server_default='{}'),

        # Current tracking
        sa.Column('current_status', sa.String(), server_default='active'),
        sa.Column('change_detected_at', sa.DateTime(), nullable=True),
        sa.Column('change_description', sa.Text(), nullable=True),

        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_index('ix_advice_signal_link_advice', 'advice_signal_links', ['advice_id'])
    op.create_index('ix_advice_signal_link_signal', 'advice_signal_links', ['signal_id'])
    op.create_index('ix_advice_signal_link_status', 'advice_signal_links', ['current_status'])


def downgrade() -> None:
    op.drop_index('ix_advice_signal_link_status')
    op.drop_index('ix_advice_signal_link_signal')
    op.drop_index('ix_advice_signal_link_advice')
    op.drop_table('advice_signal_links')
