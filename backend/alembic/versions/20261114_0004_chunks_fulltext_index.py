"""full-text search index on chunks

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # An expression index, not a stored column: nothing to keep in sync, and existing chunks
    # are indexed by this statement itself (no re-processing of documents needed).
    op.execute(
        "CREATE INDEX ix_chunks_text_fts ON chunks "
        "USING gin (to_tsvector('english'::regconfig, text))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_chunks_text_fts")
