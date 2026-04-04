"""Initial schema — all tables from models.py

Revision ID: 001
Revises: None
Create Date: 2026-04-04
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Users ---
    op.create_table(
        'users',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('email', sa.String(), nullable=False, unique=True),
        sa.Column('name', sa.String()),
        sa.Column('avatar_url', sa.String()),
        sa.Column('google_id', sa.String(), unique=True),
        sa.Column('risk_tolerance', sa.String(), server_default='moderate'),
        sa.Column('investment_horizon', sa.String(), server_default='1 year'),
        sa.Column('monthly_income_bracket', sa.String()),
        sa.Column('tax_bracket', sa.Integer(), server_default='30'),
        sa.Column('country', sa.String(), server_default='IN'),
        sa.Column('state', sa.String()),
        sa.Column('experience_level', sa.String(), server_default='intermediate'),
        sa.Column('avoid_sectors', sa.JSON(), server_default='[]'),
        sa.Column('preferred_instruments', sa.JSON(), server_default='[]'),
        sa.Column('notification_prefs', sa.JSON(), server_default='{}'),
        sa.Column('linkedin_connected', sa.Boolean(), server_default='false'),
        sa.Column('linkedin_token', sa.Text()),
        sa.Column('twitter_connected', sa.Boolean(), server_default='false'),
        sa.Column('twitter_token', sa.Text()),
        sa.Column('subscription_tier', sa.String(), server_default='free'),
        sa.Column('subscription_expires', sa.DateTime()),
        sa.Column('queries_used_this_month', sa.Integer(), server_default='0'),
        sa.Column('queries_reset_date', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('last_login', sa.DateTime()),
    )
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_google_id', 'users', ['google_id'])

    # --- Portfolio Items ---
    op.create_table(
        'portfolio_items',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('instrument_type', sa.String()),
        sa.Column('quantity', sa.Float()),
        sa.Column('avg_buy_price', sa.Float()),
        sa.Column('buy_date', sa.DateTime()),
        sa.Column('current_price', sa.Float()),
        sa.Column('sector', sa.String()),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_portfolio_user_symbol', 'portfolio_items', ['user_id', 'symbol'])

    # --- Signals ---
    op.create_table(
        'signals',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('content', sa.Text()),
        sa.Column('source', sa.String()),
        sa.Column('source_agent', sa.String()),
        sa.Column('source_tier', sa.Integer()),
        sa.Column('signal_type', sa.String()),
        sa.Column('urgency', sa.String()),
        sa.Column('importance_score', sa.Float()),
        sa.Column('confidence', sa.Float()),
        sa.Column('geography', sa.String()),
        sa.Column('sentiment', sa.String()),
        sa.Column('entities_mentioned', sa.JSON(), server_default='[]'),
        sa.Column('sectors_affected', sa.JSON(), server_default='{}'),
        sa.Column('india_impact_analysis', sa.Text()),
        sa.Column('chain_effects', sa.JSON(), server_default='[]'),
        sa.Column('stage', sa.String(), server_default='watch'),
        sa.Column('lifecycle_data', sa.JSON(), server_default='{}'),
        sa.Column('resolution_conditions', sa.JSON(), server_default='[]'),
        sa.Column('probability_scenarios', sa.JSON(), server_default='{}'),
        sa.Column('early_warning_signals', sa.JSON(), server_default='{}'),
        sa.Column('corroborated_by', sa.JSON(), server_default='[]'),
        sa.Column('corroboration_boost', sa.Float(), server_default='0'),
        sa.Column('final_weight', sa.Float()),
        sa.Column('content_hash', sa.String()),
        sa.Column('detected_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime()),
    )
    op.create_index('ix_signals_content_hash', 'signals', ['content_hash'])

    # --- Advice Records ---
    op.create_table(
        'advice_records',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('triggering_signals', sa.JSON(), server_default='[]'),
        sa.Column('user_query', sa.Text()),
        sa.Column('allocation_plan', sa.JSON()),
        sa.Column('sectors_to_buy', sa.JSON(), server_default='[]'),
        sa.Column('sectors_to_avoid', sa.JSON(), server_default='[]'),
        sa.Column('rebalancing_triggers', sa.JSON(), server_default='[]'),
        sa.Column('tax_optimizations', sa.JSON(), server_default='[]'),
        sa.Column('narrative', sa.Text()),
        sa.Column('reasoning_chain', sa.JSON()),
        sa.Column('confidence_score', sa.Float()),
        sa.Column('review_date', sa.DateTime()),
        sa.Column('market_snapshot', sa.JSON()),
        sa.Column('performance_30d', sa.JSON()),
        sa.Column('performance_90d', sa.JSON()),
        sa.Column('performance_180d', sa.JSON()),
        sa.Column('advice_rating', sa.String()),
        sa.Column('performance_notes', sa.Text()),
        sa.Column('critic_verdict', sa.String()),
        sa.Column('critic_notes', sa.Text()),
        sa.Column('revision_count', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_advice_user_created', 'advice_records', ['user_id', 'created_at'])

    # --- Agent Performance ---
    op.create_table(
        'agent_performance',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('agent_name', sa.String(), nullable=False),
        sa.Column('total_runs', sa.Integer(), server_default='0'),
        sa.Column('successful_runs', sa.Integer(), server_default='0'),
        sa.Column('accuracy_rate', sa.Float()),
        sa.Column('avg_latency_ms', sa.Float()),
        sa.Column('signal_type_accuracy', sa.JSON(), server_default='{}'),
        sa.Column('known_biases', sa.JSON(), server_default='{}'),
        sa.Column('last_calibration', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_agent_performance_name', 'agent_performance', ['agent_name'])

    # --- User Alerts ---
    op.create_table(
        'user_alerts',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('signal_id', sa.String(), sa.ForeignKey('signals.id')),
        sa.Column('alert_type', sa.String()),
        sa.Column('title', sa.String()),
        sa.Column('message', sa.Text()),
        sa.Column('severity', sa.String()),
        sa.Column('is_read', sa.Boolean(), server_default='false'),
        sa.Column('action_required', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # --- Subscriptions ---
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('tier', sa.String(), nullable=False),
        sa.Column('razorpay_sub_id', sa.String(), unique=True),
        sa.Column('status', sa.String()),
        sa.Column('current_period_start', sa.DateTime()),
        sa.Column('current_period_end', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('subscriptions')
    op.drop_table('user_alerts')
    op.drop_table('agent_performance')
    op.drop_table('advice_records')
    op.drop_table('signals')
    op.drop_table('portfolio_items')
    op.drop_table('users')
