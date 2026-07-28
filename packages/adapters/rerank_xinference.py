"""Xinference Rerank Adapter。"""

from __future__ import annotations

import httpx


class XinferenceRerankAdapter:
    def __init__(self, base_url: str, model_uid: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.model_uid = model_uid
        self.api_key = api_key

    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[dict]:
        """返回 [{index, score, document}, ...] 按分数降序。"""
        if not documents:
            return []
        url = f"{self.base_url}/v1/rerank"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict = {
            "model": self.model_uid,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results") or data.get("data") or []
        ranked: list[dict] = []
        for item in results:
            idx = item.get("index")
            score = item.get("relevance_score", item.get("score", 0.0))
            if idx is None:
                continue
            ranked.append(
                {
                    "index": int(idx),
                    "score": float(score),
                    "document": documents[int(idx)]
                    if 0 <= int(idx) < len(documents)
                    else "",
                }
            )
        ranked.sort(key=lambda x: x["score"], reverse=True)
        if top_n is not None:
            ranked = ranked[:top_n]
        return ranked
