"""narrative_space 增加 source_text / estimated_duration_sec。

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    count = conn.execute(
        text(
            """
            SELECT COUNT(1) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND COLUMN_NAME = :column_name
            """
        ),
        {"table_name": table, "column_name": column},
    ).scalar()
    return bool(int(count or 0))


def upgrade() -> None:
    if not _has_column("narrative_space", "source_text"):
        op.execute(
            "ALTER TABLE narrative_space ADD COLUMN source_text MEDIUMTEXT NULL"
        )
    if not _has_column("narrative_space", "estimated_duration_sec"):
        op.execute(
            "ALTER TABLE narrative_space "
            "ADD COLUMN estimated_duration_sec DOUBLE NULL"
        )


def downgrade() -> None:
    if _has_column("narrative_space", "estimated_duration_sec"):
        op.execute(
            "ALTER TABLE narrative_space DROP COLUMN estimated_duration_sec"
        )
    if _has_column("narrative_space", "source_text"):
        op.execute("ALTER TABLE narrative_space DROP COLUMN source_text")
