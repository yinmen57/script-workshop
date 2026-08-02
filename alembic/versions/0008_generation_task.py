"""生成任务表 generation_task：Celery 调度与 claim。

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-02
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = "DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)"
_TS_UPD = (
    "DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) "
    "ON UPDATE CURRENT_TIMESTAMP(3)"
)


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        text(
            "SELECT COUNT(1) AS c FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = :n"
        ),
        {"n": name},
    ).mappings().first()
    return bool(row and int(row["c"]) > 0)


def upgrade() -> None:
    if _has_table("generation_task"):
        return
    op.execute(
        f"""
        CREATE TABLE generation_task (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          job_run_id VARCHAR(32) NOT NULL,
          kind VARCHAR(32) NOT NULL,
          provider VARCHAR(32) NOT NULL,
          model_name VARCHAR(128) NOT NULL DEFAULT '',
          biz_ref_type VARCHAR(32) NOT NULL,
          biz_ref_id VARCHAR(32) NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'pending',
          provider_task_id VARCHAR(128) NULL,
          claim_owner VARCHAR(64) NULL,
          claim_until DATETIME(3) NULL,
          attempt INT NOT NULL DEFAULT 0,
          stage_snapshot JSON NULL,
          error TEXT NULL,
          oss_uri VARCHAR(1024) NULL,
          result_url VARCHAR(1024) NULL,
          video_job_id VARCHAR(32) NULL,
          submitted_at DATETIME(3) NULL,
          last_polled_at DATETIME(3) NULL,
          created_at {_TS},
          updated_at {_TS_UPD},
          finished_at DATETIME(3) NULL,
          INDEX idx_gen_tenant_status_claim (tenant_id, status, claim_until),
          INDEX idx_gen_status_polled (status, last_polled_at),
          INDEX idx_gen_job_run (job_run_id),
          INDEX idx_gen_provider_task (provider_task_id)
        ) ENGINE=InnoDB
        """
    )


def downgrade() -> None:
    if _has_table("generation_task"):
        op.execute("DROP TABLE generation_task")
