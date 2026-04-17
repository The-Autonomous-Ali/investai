"""Add source_region column and unique content_hash index for ingestion pipeline.

Revision ID: 006
Revises: 005
Create Date: 2026-04-17

Adds the provenance columns needed by the new enterprise ingestion layer
(see docs/superpowers/plans/2026-04-17-enterprise-data-layer.md).

- source_region: us | eu | uk | jp | cn | in | global — where the SOURCE
  is based (different from `geography`, which is what the signal AFFECTS).
  Nullable for backward compatibility with existing rows.

- content_hash already exists on the model with a plain index; this
  migration upgrades it to a UNIQUE index so Redis-level dedup can rely
  on the database as the source of truth.

NOTE: A unique-constraint upgrade can fail if duplicate rows already
exist. To make the migration safe, we first delete exact-hash duplicates
keeping the earliest row.
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'signals',
        sa.Column('source_region', sa.String(), nullable=True),
    )
    op.create_index(
        'ix_signals_source_region',
        'signals',
        ['source_region'],
    )

    # Drop duplicate content_hash rows before adding unique constraint.
    # Keeps the earliest detected row per hash. Safe because duplicates
    # carry no independent analytical value (they're the same event).
    op.execute(
        """
        DELETE FROM signals
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY content_hash
                           ORDER BY detected_at ASC, id ASC
                       ) AS rn
                FROM signals
                WHERE content_hash IS NOT NULL
            ) t
            WHERE t.rn > 1
        )
        """
    )

    # Drop the old non-unique index, add a unique one.
    # Index name pattern matches SQLAlchemy's auto-naming (index=True on a column).
    op.drop_index('ix_signals_content_hash', table_name='signals', if_exists=True)
    op.create_index(
        'ix_signals_content_hash',
        'signals',
        ['content_hash'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_signals_content_hash', table_name='signals', if_exists=True)
    op.create_index(
        'ix_signals_content_hash',
        'signals',
        ['content_hash'],
        unique=False,
    )
    op.drop_index('ix_signals_source_region', table_name='signals', if_exists=True)
    op.drop_column('signals', 'source_region')
