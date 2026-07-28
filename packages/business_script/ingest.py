"""剧本文件上传：markitdown 转 Markdown，并按知识库方式切块索引。"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import project_service
from packages.domain.errors import ValidationAppError
from packages.domain.ids import new_id
from packages.governance import vector_namespace_service
from packages.infra.config import get_settings
from packages.infra.oss import build_object_key, get_s3_client, public_url

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
_SPLIT_RE = re.compile(r"^-{3,}\s*$", re.MULTILINE)
_HEADING_RE = re.compile(r"(?m)^(#{1,3}\s+.+)$")


def project_namespace(project_id: str) -> str:
    return f"script/project/{project_id}"


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


def split_markdown_for_index(markdown: str) -> list[str]:
    """按知识库语料约定切块：优先 ---，其次标题，再按长度。"""
    text = markdown.strip()
    if not text:
        return []
    parts = [block.strip() for block in _SPLIT_RE.split(text) if block.strip()]
    if len(parts) == 1 and len(parts[0]) > 1200:
        parts = _split_by_heading(parts[0])
    chunks: list[str] = []
    for part in parts:
        if len(part) <= 1200:
            chunks.append(part)
        else:
            chunks.extend(_split_by_size(part, 800, 100))
    return chunks


def _split_by_heading(text: str) -> list[str]:
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [text]
    blocks: list[str] = []
    if matches[0].start() > 0:
        head = text[: matches[0].start()].strip()
        if head:
            blocks.append(head)
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[match.start() : end].strip()
        if block:
            blocks.append(block)
    return blocks or [text]


def _split_by_size(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    out: list[str] = []
    start = 0
    step = max(size - overlap, 1)
    while start < len(text):
        out.append(text[start : start + size])
        start += step
    return out


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
    client = get_s3_client()
    extra = {}
    if content_type:
        extra["ContentType"] = content_type
    client.put_object(
        Bucket=settings.oss_bucket,
        Key=key,
        Body=data,
        **extra,
    )
    return public_url(key)


async def upload_script_file(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    filename: str,
    data: bytes,
    content_type: str | None = None,
    title: str | None = None,
    index_knowledge: bool = True,
) -> dict:
    """上传 → Markdown → 落 script_document → 可选索引进项目命名空间。"""
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

    index_result = None
    if index_knowledge:
        entries = split_markdown_for_index(markdown)
        if not entries:
            raise ValidationAppError("切块后无可用文本，无法写入知识库")
        namespace = project_namespace(project_id)
        # 覆盖写入：同项目命名空间每次上传以当前版本为准
        index_result = await vector_namespace_service.replace_texts(
            session,
            tenant_id,
            namespace=namespace,
            texts=entries,
            chunk_size=800,
            chunk_overlap=100,
        )

    return {
        "document": doc,
        "markdown_chars": len(markdown),
        "source_filename": safe_name,
        "source_format": ext,
        "source_uri": source_uri,
        "knowledge": index_result,
    }
