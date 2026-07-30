"""第三段：剧本业务作业表 job_run。

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = "DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)"
_TS_UPD = (
    "DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) "
    "ON UPDATE CURRENT_TIMESTAMP(3)"
)


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    count = conn.execute(
        text(
            """
            SELECT COUNT(1) AS c
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
            """
        ),
        {"table_name": table},
    ).scalar()
    return bool(int(count or 0))


def upgrade() -> None:
    if _has_table("job_run"):
        return
    op.execute(
        f"""
        CREATE TABLE job_run (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          kind VARCHAR(64) NOT NULL,
          dedupe_key VARCHAR(255) NOT NULL,
          label VARCHAR(255) NOT NULL DEFAULT '',
          status VARCHAR(32) NOT NULL DEFAULT 'queued',
          progress INT NOT NULL DEFAULT 0,
          payload JSON NULL,
          result JSON NULL,
          error TEXT NULL,
          cancel_requested INT NOT NULL DEFAULT 0,
          created_by VARCHAR(64) NULL,
          created_at {_TS},
          started_at DATETIME(3) NULL,
          finished_at DATETIME(3) NULL,
          updated_at {_TS_UPD},
          INDEX idx_job_run_project (tenant_id, project_id, created_at),
          INDEX idx_job_run_dedupe (tenant_id, project_id, dedupe_key, status),
          INDEX idx_job_run_status (tenant_id, status)
        ) ENGINE=InnoDB
        """
    )


def downgrade() -> None:
    if _has_table("job_run"):
        op.execute("DROP TABLE job_run")
