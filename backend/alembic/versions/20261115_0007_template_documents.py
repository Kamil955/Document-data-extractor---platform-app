"""templates get a Word document

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("docx_key", sa.String(length=512), nullable=True))
    op.add_column("templates", sa.Column("docx_filename", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("templates", "docx_filename")
    op.drop_column("templates", "docx_key")
