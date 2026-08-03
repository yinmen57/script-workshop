"""剧本文件上传：markitdown 转 Markdown 并落 script_document。

知识库索引不在这里做：按长度盲切会把一场戏拆散，
统一由 script_index_service 在结构切分完成后按叙事空间入库。
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from business.script import project_service
from framework.domain.errors import ValidationAppError
from framework.domain.ids import new_id
from framework.infra.config import get_settings
from framework.infra.oss import build_object_key, put_bytes

_ALLOWED_EXT = {
    ".md",
    ".markdown",
    ".txt",
    ".docx",
    ".pdf",
    ".html",
    ".htm",
    ".pptx",
    ".xlsx",
    ".csv",
}


def convert_file_to_markdown(filename: str, data: bytes) -> str:
    """把上传文件转为 Markdown 文本。纯文本直接解码，其余走 markitdown。"""
    if not data:
        raise ValidationAppError("上传文件为空")
    name = Path(filename or "").name
    ext = Path(name).suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise ValidationAppError(
            f"不支持的文件格式：{ext or '(无扩展名)'}，"
            f"允许 {', '.join(sorted(_ALLOWED_EXT))}"
        )

    if ext in {".md", ".markdown", ".txt"}:
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                text = None
        if text is None:
            raise ValidationAppError("文本文件编码无法识别，请使用 UTF-8")
        markdown = text.strip()
    else:
        try:
            from markitdown import MarkItDown
        except ImportError as exc:
            raise ValidationAppError(
                "服务未安装 markitdown，无法转换该格式"
            ) from exc
        converter = MarkItDown(enable_plugins=False)
        result = converter.convert_stream(BytesIO(data), file_extension=ext)
        markdown = (getattr(result, "text_content", None) or "").strip()

    if not markdown:
        raise ValidationAppError("转换后内容为空，请检查源文件")
    return markdown


def _store_original(
    *,
    tenant_id: str,
    project_id: str,
    document_id: str,
    filename: str,
    data: bytes,
    content_type: str | None,
) -> str | None:
    settings = get_settings()
    if not settings.oss_enabled:
        return None
    key = build_object_key(tenant_id, project_id, document_id, filename)
    return put_bytes(key, data, content_type=content_type)


async def upload_script_file(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    filename: str,
    data: bytes,
    content_type: str | None = None,
    title: str | None = None,
) -> dict:
    """上传 → Markdown → 落 script_document。索引见 script_index_service。"""
    await project_service.require_project(session, tenant_id, project_id)
    safe_name = Path(filename or "script.bin").name
    markdown = convert_file_to_markdown(safe_name, data)
    doc_title = (title or "").strip() or Path(safe_name).stem or "未命名剧本"
    ext = Path(safe_name).suffix.lower().lstrip(".") or "bin"

    # 先占位 document id，便于 OSS 路径稳定
    document_id = new_id("sdoc")
    source_uri = _store_original(
        tenant_id=tenant_id,
        project_id=project_id,
        document_id=document_id,
        filename=safe_name,
        data=data,
        content_type=content_type,
    )

    doc = await project_service.add_script(
        session,
        tenant_id,
        project_id,
        {
            "id": document_id,
            "raw_text": markdown,
            "title": doc_title,
            "source_filename": safe_name,
            "source_format": ext,
            "source_uri": source_uri,
        },
    )

    return {
        "document": doc,
        "markdown_chars": len(markdown),
        "source_filename": safe_name,
        "source_format": ext,
        "source_uri": source_uri,
    }
