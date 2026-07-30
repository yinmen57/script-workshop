"""第四段：成片视频任务表 video_job。

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
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
    if _has_table("video_job"):
        return
    op.execute(
        f"""
        CREATE TABLE video_job (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          video_prompt_id VARCHAR(32) NOT NULL,
          narrative_space_id VARCHAR(32) NOT NULL,
          provider_job_id VARCHAR(128) NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'queued',
          oss_uri VARCHAR(1024) NULL,
          result_url VARCHAR(1024) NULL,
          error TEXT NULL,
          duration_sec DOUBLE NULL,
          generation_config JSON NULL,
          created_at {_TS},
          finished_at DATETIME(3) NULL,
          updated_at {_TS_UPD},
          INDEX idx_video_job_project (tenant_id, project_id),
          INDEX idx_video_job_prompt (tenant_id, video_prompt_id),
          INDEX idx_video_job_ns (tenant_id, narrative_space_id)
        ) ENGINE=InnoDB
        """
    )


def downgrade() -> None:
    if _has_table("video_job"):
        op.execute("DROP TABLE video_job")
