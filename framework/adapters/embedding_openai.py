"""OpenAI 兼容 Embedding Adapter（对接外部 Xinference）。"""

from __future__ import annotations

import httpx


class OpenAICompatibleEmbeddingAdapter:
    def __init__(self, base_url: str, api_key: str, model_uid: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_uid = model_uid

    async def embed(self, texts: list[str]) -> list[list[float]]:
        url = f"{self.base_url}/v1/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model_uid, "input": texts}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()["data"]
            return [item["embedding"] for item in data]

    async def ping(self) -> dict:
        vectors = await self.embed(["ping"])
        return {"ok": True, "dimension": len(vectors[0]) if vectors else 0}
