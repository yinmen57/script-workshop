# -*- coding: utf-8 -*-
"""model_catalog：业务类目与通用管理规格。"""

from __future__ import annotations

import pytest

from framework.domain.errors import ValidationAppError
from framework.governance.model_catalog import DEFAULT_MODEL_CATALOG, ModelCatalog, ModelTypeSpec
from framework.governance.model_service import get_model_catalog


def test_default_catalog_groups() -> None:
    public = get_model_catalog()
    ids = [c["category_id"] for c in public["categories"]]
    assert ids == ["language", "audio", "image", "video", "retrieval"]
    language = public["categories"][0]
    assert language["types"][0]["type_id"] == "chat"
    retrieval = next(c for c in public["categories"] if c["category_id"] == "retrieval")
    assert {t["type_id"] for t in retrieval["types"]} == {"embedding", "rerank"}


def test_catalog_validate_and_labels() -> None:
    cat = DEFAULT_MODEL_CATALOG
    assert cat.label("chat") == "语言模型"
    assert cat.requires_api_key_runtime("chat") is True
    assert cat.requires_api_key_runtime("embedding") is False
    with pytest.raises(ValidationAppError):
        cat.validate_fields(model_type="nope", dimension=None)


def test_custom_catalog_rejects_duplicate() -> None:
    spec = ModelTypeSpec(
        type_id="chat",
        label="x",
        category_id="c",
        category_label="C",
    )
    with pytest.raises(ValueError, match="重复"):
        ModelCatalog((spec, spec))
