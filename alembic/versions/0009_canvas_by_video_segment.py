"""画布快照改挂视频片段：canvas_snapshot.video_segment_id。

画布单位 = 视频片段（≤15s），不再挂叙事空间。
本地无旧用户：直接重建表，不迁移历史布局。

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = "DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)"
_TS_UPD = (
    "DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) "
    "ON UPDATE CURRENT_TIMESTAMP(3)"
)


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS canvas_snapshot")
    op.execute(
        f"""
        CREATE TABLE canvas_snapshot (
          id VARCHAR(32) PRIMARY KEY,
          tenant_id VARCHAR(32) NOT NULL,
          video_segment_id VARCHAR(32) NOT NULL,
          nodes JSON NOT NULL,
          edges JSON NOT NULL,
          viewport JSON NULL,
          version INT NOT NULL DEFAULT 1,
          created_at {_TS},
          updated_at {_TS_UPD},
          UNIQUE KEY uq_canvas_seg_ver (video_segment_id, version),
          INDEX idx_canvas_seg (tenant_id, video_segment_id)
        ) ENGINE=InnoDB
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS canvas_snapshot")
    op.execute(
        f"""
        CREATE TABLE canvas_snapshot (
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
