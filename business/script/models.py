"""剧本业务表 ORM 模型：Alembic schema 唯一来源。

服务层仍可用裸 SQL 查询；本模块只供迁移与结构对照。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


_DT = DATETIME(fsp=3)
_TS = text("CURRENT_TIMESTAMP(3)")


class ScriptProject(Base):
    __tablename__ = "script_project"
    __table_args__ = (Index("idx_script_project_tenant", "tenant_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    style_bible: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class ScriptDocument(Base):
    __tablename__ = "script_document"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_script_doc_version"),
        Index("idx_script_doc_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False, server_default="")
    raw_text: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    parse_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="pending"
    )
    parse_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class CharacterAsset(Base):
    __tablename__ = "character_asset"
    __table_args__ = (
        UniqueConstraint("project_id", "character_key", name="uq_character_key"),
        Index("idx_character_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    character_key: Mapped[str] = mapped_column(String(128), nullable=False)
    appearance_anchor: Mapped[str] = mapped_column(Text, nullable=False)
    costume_baseline: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ready")
    record_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ai"
    )
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class PropAsset(Base):
    __tablename__ = "prop_asset"
    __table_args__ = (
        UniqueConstraint("project_id", "prop_key", name="uq_prop_key"),
        Index("idx_prop_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_character_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prop_key: Mapped[str] = mapped_column(String(256), nullable=False)
    prop_type: Mapped[str] = mapped_column(String(64), nullable=False)
    prop_name: Mapped[str] = mapped_column(String(128), nullable=False)
    visual_anchor: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, server_default="owned")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ready")
    record_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ai"
    )
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class MaterialPrompt(Base):
    __tablename__ = "material_prompt"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "target_type",
            "target_id",
            "version",
            name="uq_material_prompt_ver",
        ),
        Index("idx_material_prompt_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_text: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    record_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ai"
    )
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class Episode(Base):
    __tablename__ = "episode"
    __table_args__ = (
        UniqueConstraint("project_id", "ordinal", name="uq_episode_ordinal"),
        Index("idx_episode_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    record_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ai"
    )
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class SceneSpace(Base):
    """地点身份：剧本内 canonical_key 唯一，作跨集视觉一致性锚点。

    与 narrative_space（成片单位）并存，不合并。
    """

    __tablename__ = "scene_space"
    __table_args__ = (
        UniqueConstraint("project_id", "canonical_key", name="uq_scene_space_canonical"),
        Index("idx_scene_space_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    anchor: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    record_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ai"
    )
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class NarrativeSpace(Base):
    """叙事空间：语义完整的一段戏，长度不受模型上限约束。

    成片切分下沉到 video_segment；本层只回答「哪里该断开成另一段戏」。
    """

    __tablename__ = "narrative_space"
    __table_args__ = (
        UniqueConstraint("episode_id", "ordinal", name="uq_ns_ordinal"),
        Index("idx_ns_episode", "tenant_id", "episode_id"),
        Index("idx_ns_project", "tenant_id", "project_id"),
        Index("idx_ns_scene_space", "tenant_id", "scene_space_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    episode_id: Mapped[str] = mapped_column(String(32), nullable=False)
    scene_space_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False, server_default="")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_place: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_text: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    estimated_duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 语义切分产物：节拍类型 / 氛围 / 断开理由；segment_source 区分规则与 LLM
    beat_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mood: Mapped[str | None] = mapped_column(String(128), nullable=True)
    boundary_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    segment_source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="rule"
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    record_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ai"
    )
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class VideoSegment(Base):
    """视频片段：叙事空间内的成片与画布单元，单段不超过模型上限（15 秒）。

    由该空间连续若干分镜聚合而成，边界由 LLM 按分镜内容判定（能否一次连贯拍完），
    是 video_prompt / video_job / canvas_snapshot 的挂载层。
    """

    __tablename__ = "video_segment"
    __table_args__ = (
        UniqueConstraint(
            "narrative_space_id", "ordinal", name="uq_video_segment_ordinal"
        ),
        Index("idx_video_segment_ns", "tenant_id", "narrative_space_id"),
        Index("idx_video_segment_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    narrative_space_id: Mapped[str] = mapped_column(String(32), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False, server_default="")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    shot_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_text: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    record_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ai"
    )
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class ShotPlan(Base):
    __tablename__ = "shot_plan"
    __table_args__ = (
        UniqueConstraint("narrative_space_id", "ordinal", name="uq_shot_ordinal"),
        Index("idx_shot_ns", "tenant_id", "narrative_space_id"),
        Index("idx_shot_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    narrative_space_id: Mapped[str] = mapped_column(String(32), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    beat: Mapped[str | None] = mapped_column(Text, nullable=True)
    character_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    prop_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    camera: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    record_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ai"
    )
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class CostumeChange(Base):
    """角色造型变化：角色 × 集 × 叙事空间。"""

    __tablename__ = "costume_change"
    __table_args__ = (
        Index("idx_costume_project", "tenant_id", "project_id"),
        Index("idx_costume_character", "tenant_id", "character_id"),
        Index("idx_costume_ns", "tenant_id", "narrative_space_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    character_id: Mapped[str] = mapped_column(String(32), nullable=False)
    episode_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    narrative_space_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    change_point: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    image_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    series_wide: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    record_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ai"
    )
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class MaterialImage(Base):
    """统一图片目录：生成 / 上传 / 导入；主记录 image_url 仅作当前选中指针。"""

    __tablename__ = "material_image"
    __table_args__ = (
        UniqueConstraint("project_id", "url", name="uq_material_image_url"),
        Index("idx_material_image_project", "tenant_id", "project_id"),
        Index("idx_material_image_source", "tenant_id", "source_kind", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # 512：utf8mb4 下唯一索引长度限制（与参考项目一致）
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    origin: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="generated"
    )
    source_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prompt: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    generation_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    series_wide: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    record_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ai"
    )
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class VideoPrompt(Base):
    """成片提示词：一视频片段一段（D1）。

    narrative_space_id 为冗余列，便于按空间聚合查询。
    """

    __tablename__ = "video_prompt"
    __table_args__ = (
        UniqueConstraint(
            "video_segment_id", "version", name="uq_video_prompt_seg_ver"
        ),
        Index("idx_video_prompt_project", "tenant_id", "project_id"),
        Index("idx_video_prompt_ns", "tenant_id", "narrative_space_id"),
        Index("idx_video_prompt_segment", "tenant_id", "video_segment_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    video_segment_id: Mapped[str] = mapped_column(String(32), nullable=False)
    narrative_space_id: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_text: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_image_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    record_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="ai"
    )
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class RecordRevision(Base):
    """定版 / 人工修改 / 反悔的废稿历史（文本类记录）。"""

    __tablename__ = "record_revision"
    __table_args__ = (
        UniqueConstraint(
            "target_type",
            "target_id",
            "revision_no",
            name="uq_record_revision_no",
        ),
        Index("idx_record_revision_target", "tenant_id", "target_type", "target_id"),
        Index("idx_record_revision_project", "tenant_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_reason: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class CanvasSnapshot(Base):
    """画布快照：挂视频片段（≤15s），一片段一画布。"""

    __tablename__ = "canvas_snapshot"
    __table_args__ = (
        UniqueConstraint("video_segment_id", "version", name="uq_canvas_seg_ver"),
        Index("idx_canvas_seg", "tenant_id", "video_segment_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    video_segment_id: Mapped[str] = mapped_column(String(32), nullable=False)
    nodes: Mapped[list] = mapped_column(JSON, nullable=False)
    edges: Mapped[list] = mapped_column(JSON, nullable=False)
    viewport: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class VideoJob(Base):
    """视频片段成片任务：挂 video_prompt_id，一片段一任务。"""

    __tablename__ = "video_job"
    __table_args__ = (
        Index("idx_video_job_project", "tenant_id", "project_id"),
        Index("idx_video_job_prompt", "tenant_id", "video_prompt_id"),
        Index("idx_video_job_ns", "tenant_id", "narrative_space_id"),
        Index("idx_video_job_segment", "tenant_id", "video_segment_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    video_prompt_id: Mapped[str] = mapped_column(String(32), nullable=False)
    video_segment_id: Mapped[str] = mapped_column(String(32), nullable=False)
    narrative_space_id: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="queued")
    oss_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    result_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    finished_at: Mapped[datetime | None] = mapped_column(_DT, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)


class JobRun(Base):
    """剧本业务后台作业：投递 / 去重 / 状态机（第三段）。"""

    __tablename__ = "job_run"
    __table_args__ = (
        Index("idx_job_run_project", "tenant_id", "project_id", "created_at"),
        Index("idx_job_run_dedupe", "tenant_id", "project_id", "dedupe_key", "status"),
        Index("idx_job_run_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
    started_at: Mapped[datetime | None] = mapped_column(_DT, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(_DT, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(_DT, nullable=False, server_default=_TS)
