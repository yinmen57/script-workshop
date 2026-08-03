# -*- coding: utf-8 -*-
"""模型配置目录：按业务能力分类，统一约束与展示元数据。

一类模型（chat / audio / image …）可配置多条；运行时仍按 type 取「默认」一条。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ModelTypeSpec:
    """单种模型类型的通用管理规格。"""

    type_id: str
    label: str
    category_id: str
    category_label: str
    description: str = ""
    default_provider: str = "openai_compatible"
    # None 表示 Provider 自由填写；非空则仅允许列表内取值
    providers: tuple[str, ...] | None = None
    provider_labels: dict[str, str] = field(default_factory=dict)
    requires_dimension: bool = False
    forbids_dimension: bool = True
    # 新建时是否强制要求 api_key
    requires_api_key_on_create: bool = True
    # 运行时默认是否允许空 key（本地 Xinference 等）
    allow_empty_api_key_runtime: bool = False
    model_name_placeholder: str = ""
    base_url_placeholder: str = "https://..."
    sort_order: int = 100


class ModelCatalog:
    """模型类型注册表：校验、分组、对外 catalog API 共用。"""

    def __init__(self, specs: tuple[ModelTypeSpec, ...]) -> None:
        if not specs:
            raise ValueError("ModelCatalog 不能为空")
        ids = [s.type_id for s in specs]
        if len(ids) != len(set(ids)):
            raise ValueError("model type_id 重复")
        self._specs = tuple(sorted(specs, key=lambda s: (s.sort_order, s.type_id)))
        self._by_id = {s.type_id: s for s in self._specs}

    def get(self, type_id: str) -> ModelTypeSpec:
        spec = self._by_id.get(type_id)
        if spec is None:
            raise KeyError(type_id)
        return spec

    def has(self, type_id: str) -> bool:
        return type_id in self._by_id

    @property
    def type_ids(self) -> frozenset[str]:
        return frozenset(self._by_id)

    def label(self, type_id: str) -> str:
        spec = self._by_id.get(type_id)
        return spec.label if spec else type_id

    def validate_fields(
        self,
        *,
        model_type: str,
        dimension: int | None,
        provider: str | None = None,
    ) -> None:
        from framework.domain.errors import ValidationAppError

        if model_type not in self._by_id:
            allowed = "/".join(s.type_id for s in self._specs)
            raise ValidationAppError(f"model_type must be {allowed}")
        spec = self._by_id[model_type]
        if spec.requires_dimension and not dimension:
            raise ValidationAppError(f"{model_type} model requires dimension")
        if spec.forbids_dimension and dimension is not None:
            raise ValidationAppError(f"{model_type} model must not set dimension")
        if spec.providers is not None and provider is not None:
            p = provider.strip()
            if p and p not in spec.providers:
                names = " 或 ".join(
                    spec.provider_labels.get(x, x) for x in spec.providers
                )
                raise ValidationAppError(
                    f"{model_type} provider 须为 {' / '.join(spec.providers)}（{names}）"
                )

    def default_provider(self, model_type: str) -> str:
        return self.get(model_type).default_provider

    def requires_api_key_runtime(self, model_type: str) -> bool:
        return not self.get(model_type).allow_empty_api_key_runtime

    def to_public(self) -> dict:
        """供管理端按业务类目渲染。"""
        categories: dict[str, dict] = {}
        for spec in self._specs:
            bucket = categories.setdefault(
                spec.category_id,
                {
                    "category_id": spec.category_id,
                    "label": spec.category_label,
                    "sort_order": spec.sort_order,
                    "types": [],
                },
            )
            bucket["sort_order"] = min(bucket["sort_order"], spec.sort_order)
            item = asdict(spec)
            # 前端不需要内部字段重复
            item.pop("category_id", None)
            item.pop("category_label", None)
            item.pop("sort_order", None)
            bucket["types"].append(item)
        ordered = sorted(categories.values(), key=lambda c: c["sort_order"])
        for cat in ordered:
            cat.pop("sort_order", None)
        return {
            "categories": ordered,
            "types": [asdict(s) for s in self._specs],
        }


# 业务侧能力目录：一类可多配；运行时按 type 取默认
DEFAULT_MODEL_CATALOG = ModelCatalog(
    (
        ModelTypeSpec(
            type_id="chat",
            label="语言模型",
            category_id="language",
            category_label="语言模型",
            description="对话 / Agent / 剧本解析等文本生成",
            default_provider="openai_compatible",
            forbids_dimension=True,
            requires_api_key_on_create=True,
            allow_empty_api_key_runtime=False,
            model_name_placeholder="例如：deepseek-v4-flash-260425",
            base_url_placeholder="例如：https://ark.cn-beijing.volces.com/api/v3",
            sort_order=10,
        ),
        ModelTypeSpec(
            type_id="audio",
            label="声音模型",
            category_id="audio",
            category_label="声音模型",
            description="语音合成 / 识别等音频能力（同类可配多条）",
            default_provider="openai_compatible",
            forbids_dimension=True,
            requires_api_key_on_create=True,
            allow_empty_api_key_runtime=False,
            model_name_placeholder="例如：tts / asr 模型名",
            base_url_placeholder="例如：https://api.example.com/v1",
            sort_order=20,
        ),
        ModelTypeSpec(
            type_id="image",
            label="生图",
            category_id="image",
            category_label="生图",
            description="素材图 / 角色图等图像生成",
            default_provider="shangwu",
            providers=("shangwu", "volcengine_ark"),
            provider_labels={"shangwu": "赏舞", "volcengine_ark": "火山方舟"},
            forbids_dimension=True,
            requires_api_key_on_create=True,
            allow_empty_api_key_runtime=False,
            model_name_placeholder="例如：doubao-seedream-5-0-260128",
            base_url_placeholder="赏舞网关或方舟 Base URL",
            sort_order=30,
        ),
        ModelTypeSpec(
            type_id="video",
            label="生视频",
            category_id="video",
            category_label="生视频",
            description="镜头 / 片段视频生成",
            default_provider="shangwu",
            providers=("shangwu", "volcengine_ark"),
            provider_labels={"shangwu": "赏舞", "volcengine_ark": "火山方舟"},
            forbids_dimension=True,
            requires_api_key_on_create=True,
            allow_empty_api_key_runtime=False,
            model_name_placeholder="例如：doubao-seedance-2-0-260128",
            base_url_placeholder="赏舞网关或方舟 Base URL",
            sort_order=40,
        ),
        ModelTypeSpec(
            type_id="embedding",
            label="Embedding",
            category_id="retrieval",
            category_label="检索模型",
            description="知识库向量化",
            default_provider="openai_compatible",
            requires_dimension=True,
            forbids_dimension=False,
            requires_api_key_on_create=False,
            allow_empty_api_key_runtime=True,
            model_name_placeholder="例如：bge-m3",
            base_url_placeholder="例如：http://127.0.0.1:9997",
            sort_order=50,
        ),
        ModelTypeSpec(
            type_id="rerank",
            label="Rerank",
            category_id="retrieval",
            category_label="检索模型",
            description="检索精排",
            default_provider="xinference",
            forbids_dimension=True,
            requires_api_key_on_create=False,
            allow_empty_api_key_runtime=True,
            model_name_placeholder="例如：bge-reranker-v2-m3",
            base_url_placeholder="例如：http://127.0.0.1:9997",
            sort_order=60,
        ),
    )
)
