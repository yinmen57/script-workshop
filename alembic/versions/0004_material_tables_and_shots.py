"""第二段剩余表：地点身份 / 造型 / 图片目录 / 成片提示词 / 废稿历史；分镜补 duration。

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
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


def upgrade() -> None:
    if not _has_table("scene_space"):
        op.execute(
            f"""
            CREATE TABLE scene_space (
              id VARCHAR(32) PRIMARY KEY,
              tenant_id VARCHAR(32) NOT NULL,
              project_id VARCHAR(32) NOT NULL,
              canonical_key VARCHAR(255) NOT NULL,
              name VARCHAR(128) NOT NULL,
              anchor TEXT NULL,
              reference_image_url VARCHAR(1024) NULL,
              record_status VARCHAR(32) NOT NULL DEFAULT 'ai',
              created_at {_TS},
              updated_at {_TS_UPD},
              UNIQUE KEY uq_scene_space_canonical (project_id, canonical_key),
              INDEX idx_scene_space_project (tenant_id, project_id)
            ) ENGINE=InnoDB
            """
        )

    if not _has_column("narrative_space", "scene_space_id"):
        op.execute(
            "ALTER TABLE narrative_space "
            "ADD COLUMN scene_space_id VARCHAR(32) NULL"
        )
        op.execute(
            "CREATE INDEX idx_ns_scene_space "
            "ON narrative_space (tenant_id, scene_space_id)"
        )

    if not _has_column("shot_plan", "duration_sec"):
        op.execute(
            "ALTER TABLE shot_plan ADD COLUMN duration_sec DOUBLE NULL"
        )

    if not _has_table("costume_change"):
        op.execute(
            f"""
            CREATE TABLE costume_change (
              id VARCHAR(32) PRIMARY KEY,
              tenant_id VARCHAR(32) NOT NULL,
              project_id VARCHAR(32) NOT NULL,
              character_id VARCHAR(32) NOT NULL,
              episode_id VARCHAR(32) NULL,
              narrative_space_id VARCHAR(32) NULL,
              description TEXT NOT NULL,
              change_point VARCHAR(255) NULL,
              evidence JSON NULL,
              image_prompt TEXT NULL,
              image_url VARCHAR(1024) NULL,
              series_wide INT NOT NULL DEFAULT 0,
              record_status VARCHAR(32) NOT NULL DEFAULT 'ai',
              created_at {_TS},
              updated_at {_TS_UPD},
              INDEX idx_costume_project (tenant_id, project_id),
              INDEX idx_costume_character (tenant_id, character_id),
              INDEX idx_costume_ns (tenant_id, narrative_space_id)
            ) ENGINE=InnoDB
            """
        )

    if not _has_table("material_image"):
        op.execute(
            f"""
            CREATE TABLE material_image (
              id VARCHAR(32) PRIMARY KEY,
              tenant_id VARCHAR(32) NOT NULL,
              project_id VARCHAR(32) NOT NULL,
              url VARCHAR(512) NOT NULL,
              label VARCHAR(255) NOT NULL DEFAULT '',
              origin VARCHAR(32) NOT NULL DEFAULT 'generated',
              source_kind VARCHAR(32) NULL,
              source_id VARCHAR(32) NULL,
              prompt MEDIUMTEXT NULL,
              generation_config JSON NULL,
              series_wide INT NOT NULL DEFAULT 0,
              record_status VARCHAR(32) NOT NULL DEFAULT 'ai',
              created_at {_TS},
              updated_at {_TS_UPD},
              UNIQUE KEY uq_material_image_url (project_id, url),
              INDEX idx_material_image_project (tenant_id, project_id),
              INDEX idx_material_image_source (tenant_id, source_kind, source_id)
            ) ENGINE=InnoDB
            """
        )

    if not _has_table("video_prompt"):
        op.execute(
            f"""
            CREATE TABLE video_prompt (
              id VARCHAR(32) PRIMARY KEY,
              tenant_id VARCHAR(32) NOT NULL,
              project_id VARCHAR(32) NOT NULL,
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
              UNIQUE KEY uq_video_prompt_ns_ver (narrative_space_id, version),
              INDEX idx_video_prompt_project (tenant_id, project_id),
              INDEX idx_video_prompt_ns (tenant_id, narrative_space_id)
            ) ENGINE=InnoDB
            """
        )

    if not _has_table("record_revision"):
        op.execute(
            f"""
            CREATE TABLE record_revision (
              id VARCHAR(32) PRIMARY KEY,
              tenant_id VARCHAR(32) NOT NULL,
              project_id VARCHAR(32) NOT NULL,
              target_type VARCHAR(32) NOT NULL,
              target_id VARCHAR(32) NOT NULL,
              revision_no INT NOT NULL,
              snapshot JSON NOT NULL,
              change_reason VARCHAR(32) NOT NULL,
              created_by VARCHAR(64) NULL,
              created_at {_TS},
              UNIQUE KEY uq_record_revision_no (target_type, target_id, revision_no),
              INDEX idx_record_revision_target (tenant_id, target_type, target_id),
              INDEX idx_record_revision_project (tenant_id, project_id)
            ) ENGINE=InnoDB
            """
        )


def downgrade() -> None:
    if _has_table("record_revision"):
        op.execute("DROP TABLE record_revision")
    if _has_table("video_prompt"):
        op.execute("DROP TABLE video_prompt")
    if _has_table("material_image"):
        op.execute("DROP TABLE material_image")
    if _has_table("costume_change"):
        op.execute("DROP TABLE costume_change")
    if _has_column("shot_plan", "duration_sec"):
        op.execute("ALTER TABLE shot_plan DROP COLUMN duration_sec")
    if _has_column("narrative_space", "scene_space_id"):
        op.execute("ALTER TABLE narrative_space DROP INDEX idx_ns_scene_space")
        op.execute("ALTER TABLE narrative_space DROP COLUMN scene_space_id")
    if _has_table("scene_space"):
        op.execute("DROP TABLE scene_space")
