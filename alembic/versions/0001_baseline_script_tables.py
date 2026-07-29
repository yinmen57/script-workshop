"""剧本业务九张表 baseline（无 content_type）。

Revision ID: 0001
Revises:
Create Date: 2026-07-29

现有库：alembic stamp 0001 后升级后续 revision。
空库：alembic upgrade head 从本 revision 建表。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = "DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)"
_TS_UPD = (
    "DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) "
    "ON UPDATE CURRENT_TIMESTAMP(3)"
)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS script_project (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          name VARCHAR(128) NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'draft',
          style_bible JSON NULL,
          created_at {_TS},
          updated_at {_TS_UPD},
          INDEX idx_script_project_tenant (tenant_id, updated_at)
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS script_document (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          title VARCHAR(256) NOT NULL DEFAULT '',
          raw_text MEDIUMTEXT NOT NULL,
          version INT NOT NULL DEFAULT 1,
          parse_status VARCHAR(32) NOT NULL DEFAULT 'pending',
          parse_result JSON NULL,
          source_filename VARCHAR(512) NULL,
          source_format VARCHAR(32) NULL,
          source_uri VARCHAR(1024) NULL,
          created_at {_TS},
          updated_at {_TS_UPD},
          UNIQUE KEY uq_script_doc_version (project_id, version),
          INDEX idx_script_doc_project (tenant_id, project_id)
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS character_asset (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          name VARCHAR(128) NOT NULL,
          character_key VARCHAR(128) NOT NULL,
          appearance_anchor TEXT NOT NULL,
          costume_baseline TEXT NULL,
          personality_tags JSON NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'ready',
          record_status VARCHAR(32) NOT NULL DEFAULT 'ai',
          created_at {_TS},
          updated_at {_TS_UPD},
          UNIQUE KEY uq_character_key (project_id, character_key),
          INDEX idx_character_project (tenant_id, project_id)
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS prop_asset (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          owner_character_id VARCHAR(32) NULL,
          prop_key VARCHAR(256) NOT NULL,
          prop_type VARCHAR(64) NOT NULL,
          prop_name VARCHAR(128) NOT NULL,
          visual_anchor TEXT NOT NULL,
          scope VARCHAR(32) NOT NULL DEFAULT 'owned',
          status VARCHAR(32) NOT NULL DEFAULT 'ready',
          record_status VARCHAR(32) NOT NULL DEFAULT 'ai',
          created_at {_TS},
          updated_at {_TS_UPD},
          UNIQUE KEY uq_prop_key (project_id, prop_key),
          INDEX idx_prop_project (tenant_id, project_id)
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS material_prompt (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          target_type VARCHAR(32) NOT NULL,
          target_id VARCHAR(32) NOT NULL,
          prompt_text MEDIUMTEXT NOT NULL,
          negative_prompt TEXT NULL,
          style_ref JSON NULL,
          version INT NOT NULL DEFAULT 1,
          status VARCHAR(32) NOT NULL DEFAULT 'draft',
          record_status VARCHAR(32) NOT NULL DEFAULT 'ai',
          created_at {_TS},
          updated_at {_TS_UPD},
          UNIQUE KEY uq_material_prompt_ver (project_id, target_type, target_id, version),
          INDEX idx_material_prompt_project (tenant_id, project_id)
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS episode (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          ordinal INT NOT NULL,
          title VARCHAR(256) NOT NULL DEFAULT '',
          status VARCHAR(32) NOT NULL DEFAULT 'draft',
          record_status VARCHAR(32) NOT NULL DEFAULT 'ai',
          created_at {_TS},
          updated_at {_TS_UPD},
          UNIQUE KEY uq_episode_ordinal (project_id, ordinal),
          INDEX idx_episode_project (tenant_id, project_id)
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS narrative_space (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          episode_id VARCHAR(32) NOT NULL,
          ordinal INT NOT NULL,
          title VARCHAR(256) NOT NULL DEFAULT '',
          summary TEXT NULL,
          time_place VARCHAR(512) NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'draft',
          record_status VARCHAR(32) NOT NULL DEFAULT 'ai',
          created_at {_TS},
          updated_at {_TS_UPD},
          UNIQUE KEY uq_ns_ordinal (episode_id, ordinal),
          INDEX idx_ns_episode (tenant_id, episode_id),
          INDEX idx_ns_project (tenant_id, project_id)
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS shot_plan (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          project_id VARCHAR(32) NOT NULL,
          narrative_space_id VARCHAR(32) NOT NULL,
          ordinal INT NOT NULL,
          scene_text TEXT NULL,
          beat TEXT NULL,
          character_ids JSON NULL,
          prop_ids JSON NULL,
          camera JSON NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'draft',
          record_status VARCHAR(32) NOT NULL DEFAULT 'ai',
          created_at {_TS},
          updated_at {_TS_UPD},
          UNIQUE KEY uq_shot_ordinal (narrative_space_id, ordinal),
          INDEX idx_shot_ns (tenant_id, narrative_space_id),
          INDEX idx_shot_project (tenant_id, project_id)
        ) ENGINE=InnoDB
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS canvas_snapshot (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          narrative_space_id VARCHAR(32) NOT NULL,
          nodes JSON NOT NULL,
          edges JSON NOT NULL,
          viewport JSON NULL,
          version INT NOT NULL DEFAULT 1,
          created_at {_TS},
          updated_at {_TS_UPD},
          UNIQUE KEY uq_canvas_ns_ver (narrative_space_id, version),
          INDEX idx_canvas_ns (tenant_id, narrative_space_id)
        ) ENGINE=InnoDB
        """
    )


def downgrade() -> None:
    for table in (
        "canvas_snapshot",
        "shot_plan",
        "narrative_space",
        "episode",
        "material_prompt",
        "prop_asset",
        "character_asset",
        "script_document",
        "script_project",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
