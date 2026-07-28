"""剧本业务表：启动时 ensure，并与 init.sql 保持一致。"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _ensure_columns(
    session: AsyncSession, table: str, columns: dict[str, str]
) -> None:
    """已有表补列；列已存在则跳过。"""
    for name, ddl in columns.items():
        exists = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(1) AS c
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = :table_name
                      AND COLUMN_NAME = :column_name
                    """
                ),
                {"table_name": table, "column_name": name},
            )
        ).mappings().first()["c"]
        if int(exists):
            continue
        await session.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
    await session.commit()


async def ensure_script_schema(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS script_project (
              id VARCHAR(32) PRIMARY KEY,
              tenant_id VARCHAR(32) NOT NULL,
              name VARCHAR(128) NOT NULL,
              status VARCHAR(32) NOT NULL DEFAULT 'draft',
              content_type VARCHAR(32) NULL,
              style_bible JSON NULL,
              created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
              updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                ON UPDATE CURRENT_TIMESTAMP(3),
              INDEX idx_script_project_tenant (tenant_id, updated_at)
            ) ENGINE=InnoDB
            """
        )
    )
    await session.execute(
        text(
            """
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
              created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
              updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                ON UPDATE CURRENT_TIMESTAMP(3),
              UNIQUE KEY uq_script_doc_version (project_id, version),
              INDEX idx_script_doc_project (tenant_id, project_id)
            ) ENGINE=InnoDB
            """
        )
    )
    await _ensure_columns(
        session,
        "script_document",
        {
            "source_filename": "VARCHAR(512) NULL",
            "source_format": "VARCHAR(32) NULL",
            "source_uri": "VARCHAR(1024) NULL",
        },
    )
    await session.execute(
        text(
            """
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
              created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
              updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                ON UPDATE CURRENT_TIMESTAMP(3),
              UNIQUE KEY uq_character_key (project_id, character_key),
              INDEX idx_character_project (tenant_id, project_id)
            ) ENGINE=InnoDB
            """
        )
    )
    await session.execute(
        text(
            """
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
              created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
              updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                ON UPDATE CURRENT_TIMESTAMP(3),
              UNIQUE KEY uq_prop_key (project_id, prop_key),
              INDEX idx_prop_project (tenant_id, project_id)
            ) ENGINE=InnoDB
            """
        )
    )
    await session.execute(
        text(
            """
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
              created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
              updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                ON UPDATE CURRENT_TIMESTAMP(3),
              UNIQUE KEY uq_material_prompt_ver (project_id, target_type, target_id, version),
              INDEX idx_material_prompt_project (tenant_id, project_id)
            ) ENGINE=InnoDB
            """
        )
    )
    await session.commit()
