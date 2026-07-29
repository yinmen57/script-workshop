"""删除 script_project.content_type。

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        text(
            """
            SELECT COUNT(1) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'script_project'
              AND COLUMN_NAME = 'content_type'
            """
        )
    ).scalar()
    if int(exists or 0):
        op.execute("ALTER TABLE script_project DROP COLUMN content_type")


def downgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        text(
            """
            SELECT COUNT(1) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'script_project'
              AND COLUMN_NAME = 'content_type'
            """
        )
    ).scalar()
    if not int(exists or 0):
        op.execute(
            "ALTER TABLE script_project ADD COLUMN content_type VARCHAR(32) NULL"
        )
