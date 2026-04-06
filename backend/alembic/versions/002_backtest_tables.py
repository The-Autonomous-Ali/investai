"""Backtest harness tables — sector_prices + kg_edge_stats

Revision ID: 002
Revises: 001
Create Date: 2026-04-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sector_prices',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(length=32), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('close', sa.Numeric(14, 4), nullable=False),
        sa.Column('returns_1d', sa.Numeric(10, 6)),
        sa.Column('returns_5d', sa.Numeric(10, 6)),
        sa.Column('returns_30d', sa.Numeric(10, 6)),
        sa.Column('source', sa.String(length=16), nullable=False, server_default='yfinance'),
        sa.Column('ingested_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('symbol', 'date', name='uq_sector_prices_symbol_date'),
    )
    op.create_index('ix_sector_prices_symbol_date', 'sector_prices', ['symbol', 'date'])

    op.create_table(
        'kg_edge_stats',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('event_name', sa.String(length=128), nullable=False),
        sa.Column('sector', sa.String(length=64), nullable=False),
        sa.Column('lag_days', sa.Integer(), nullable=False),
        sa.Column('sample_size', sa.Integer(), nullable=False),
        sa.Column('hits', sa.Integer(), nullable=False),
        sa.Column('hit_rate', sa.Numeric(6, 4), nullable=False),
        sa.Column('avg_alpha', sa.Numeric(10, 6), nullable=False),
        sa.Column('alpha_stddev', sa.Numeric(10, 6), nullable=False),
        sa.Column('ci95_low', sa.Numeric(10, 6), nullable=False),
        sa.Column('ci95_high', sa.Numeric(10, 6), nullable=False),
        sa.Column('measured_strength', sa.Numeric(5, 4), nullable=False),
        sa.Column('predicted_direction', sa.String(length=8), nullable=False),
        sa.Column('calibrated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('event_name', 'sector', 'lag_days', name='uq_kg_edge_stats_event_sector_lag'),
    )
    op.create_index('ix_kg_edge_stats_event_type', 'kg_edge_stats', ['event_type'])
    op.create_index('ix_kg_edge_stats_sector', 'kg_edge_stats', ['sector'])


def downgrade() -> None:
    op.drop_index('ix_kg_edge_stats_sector', table_name='kg_edge_stats')
    op.drop_index('ix_kg_edge_stats_event_type', table_name='kg_edge_stats')
    op.drop_table('kg_edge_stats')
    op.drop_index('ix_sector_prices_symbol_date', table_name='sector_prices')
    op.drop_table('sector_prices')
