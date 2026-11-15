"""extractions become background jobs

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Rows that already exist are finished extractions, so the defaults below describe them
    # correctly. The defaults are dropped afterwards: new rows get their values from the code.
    op.add_column(
        "extractions",
        sa.Column("status", sa.String(length=20), server_default="completed", nullable=False),
    )
    op.add_column(
        "extractions",
        sa.Column(
            "fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "extractions",
        sa.Column("retrieval_limit", sa.Integer(), server_default="8", nullable=False),
    )
    op.add_column("extractions", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("extractions", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("extractions", "status", server_default=None)
    op.alter_column("extractions", "fields", server_default=None)
    op.alter_column("extractions", "retrieval_limit", server_default=None)
    # The worker looks for waiting extractions: a small index on the status keeps that cheap.
    op.create_index(op.f("ix_extractions_status"), "extractions", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_extractions_status"), table_name="extractions")
    op.drop_column("extractions", "started_at")
    op.drop_column("extractions", "error")
    op.drop_column("extractions", "retrieval_limit")
    op.drop_column("extractions", "fields")
    op.drop_column("extractions", "status")
