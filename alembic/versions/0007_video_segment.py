"""视频片段层：叙事空间改语义单元，成片切分下沉到 video_segment。

- narrative_space 增加语义切分字段（节拍 / 氛围 / 断开理由 / 来源）
- 新建 video_segment（≤15 秒生成单元）
- video_prompt / video_job 改挂 video_segment_id

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
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


_NS_COLUMNS = (
    ("beat_type", "VARCHAR(32) NULL"),
    ("mood", "VARCHAR(128) NULL"),
    ("boundary_reason", "VARCHAR(512) NULL"),
    ("segment_source", "VARCHAR(16) NOT NULL DEFAULT 'rule'"),
)


def _create_video_prompt() -> None:
    op.execute(
        f"""
        CREATE TABLE video_prompt (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          video_segment_id VARCHAR(32) NOT NULL,
          narrative_space_id VARCHAR(32) NOT NULL,
          prompt_text MEDIUMTEXT NOT NULL,
          negative_prompt TEXT NULL,
          ref_image_ids JSON NULL,
          duration_sec DOUBLE NULL,
          version INT NOT NULL DEFAULT 1,
          status VARCHAR(32) NOT NULL DEFAULT 'draft',
          record_status VARCHAR(32) NOT NULL DEFAULT 'ai',
          created_at {_TS},
          updated_at {_TS_UPD},
          UNIQUE KEY uq_video_prompt_seg_ver (video_segment_id, version),
          INDEX idx_video_prompt_project (tenant_id, project_id),
          INDEX idx_video_prompt_ns (tenant_id, narrative_space_id),
          INDEX idx_video_prompt_segment (tenant_id, video_segment_id)
        ) ENGINE=InnoDB
        """
    )


def _create_video_job() -> None:
    op.execute(
        f"""
        CREATE TABLE video_job (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          video_prompt_id VARCHAR(32) NOT NULL,
          video_segment_id VARCHAR(32) NOT NULL,
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
          INDEX idx_video_job_ns (tenant_id, narrative_space_id),
          INDEX idx_video_job_segment (tenant_id, video_segment_id)
        ) ENGINE=InnoDB
        """
    )


def upgrade() -> None:
    for column, ddl in _NS_COLUMNS:
        if not _has_column("narrative_space", column):
            op.execute(f"ALTER TABLE narrative_space ADD COLUMN {column} {ddl}")

    if not _has_table("video_segment"):
        op.execute(
            f"""
            CREATE TABLE video_segment (
              id VARCHAR(32) PRIMARY KEY,
              tenant_id VARCHAR(32) NOT NULL,
              project_id VARCHAR(32) NOT NULL,
              narrative_space_id VARCHAR(32) NOT NULL,
              ordinal INT NOT NULL,
              title VARCHAR(256) NOT NULL DEFAULT '',
              summary TEXT NULL,
              shot_ids JSON NULL,
              source_text MEDIUMTEXT NULL,
              duration_sec DOUBLE NULL,
              status VARCHAR(32) NOT NULL DEFAULT 'draft',
              record_status VARCHAR(32) NOT NULL DEFAULT 'ai',
              created_at {_TS},
              updated_at {_TS_UPD},
              UNIQUE KEY uq_video_segment_ordinal (narrative_space_id, ordinal),
              INDEX idx_video_segment_ns (tenant_id, narrative_space_id),
              INDEX idx_video_segment_project (tenant_id, project_id)
            ) ENGINE=InnoDB
            """
        )

    # 挂载层从叙事空间改为视频片段，历史行无法补出片段归属，直接重建
    if _has_table("video_job"):
        op.execute("DROP TABLE video_job")
    if _has_table("video_prompt"):
        op.execute("DROP TABLE video_prompt")
    _create_video_prompt()
    _create_video_job()


def downgrade() -> None:
    if _has_table("video_job"):
        op.execute("DROP TABLE video_job")
    if _has_table("video_prompt"):
        op.execute("DROP TABLE video_prompt")
    if _has_table("video_segment"):
        op.execute("DROP TABLE video_segment")
    for column, _ in _NS_COLUMNS:
        if _has_column("narrative_space", column):
            op.execute(f"ALTER TABLE narrative_space DROP COLUMN {column}")
