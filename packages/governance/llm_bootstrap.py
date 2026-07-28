"""按 .env 的 LLM_* 登记默认 Chat 模型到 model_config。"""

from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.infra.config import get_settings
from packages.infra.crypto import encrypt_secret

logger = logging.getLogger(__name__)

# 固定 ID：本地以 .env 为唯一来源，重复启动覆盖同条记录
DEFAULT_LLM_MODEL_ID = "mdl_ark_llm_001"
DEFAULT_LLM_TENANT_ID = "ten_demo"


async def ensure_default_llm_model(session: AsyncSession) -> str:
    settings = get_settings()
    cipher = encrypt_secret(settings.llm_api_key)
    extra = json.dumps(
        {"timeout_seconds": settings.llm_timeout, "source": "env:LLM_*"},
        ensure_ascii=False,
    )
    await session.execute(
        text(
            """
            INSERT INTO model_config
              (id, tenant_id, name, provider, model_type, model_name, base_url,
               api_key_cipher, dimension, extra, status)
            VALUES
              (:id, :tenant_id, :name, :provider, 'chat', :model_name, :base_url,
               :api_key_cipher, NULL, CAST(:extra AS JSON), 'enabled')
            ON DUPLICATE KEY UPDATE
              name = VALUES(name),
              provider = VALUES(provider),
              model_name = VALUES(model_name),
              base_url = VALUES(base_url),
              api_key_cipher = VALUES(api_key_cipher),
              extra = VALUES(extra),
              status = 'enabled'
            """
        ),
        {
            "id": DEFAULT_LLM_MODEL_ID,
            "tenant_id": DEFAULT_LLM_TENANT_ID,
            "name": f"Ark {settings.llm_model}",
            "provider": "volcengine_ark",
            "model_name": settings.llm_model,
            "base_url": settings.llm_base_url.rstrip("/"),
            "api_key_cipher": cipher,
            "extra": extra,
        },
    )
    await session.commit()
    logger.info(
        "default llm model ready: id=%s model=%s",
        DEFAULT_LLM_MODEL_ID,
        settings.llm_model,
    )
    return DEFAULT_LLM_MODEL_ID
