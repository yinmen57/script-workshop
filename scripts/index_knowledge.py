"""把应用空间的 knowledge/ 语料索引进向量命名空间。

用法：
    python scripts/index_knowledge.py --slug script-workshop
    python scripts/index_knowledge.py --slug script-workshop --check "角色三视图怎么写"

语料约定：knowledge/manifest.yaml 声明 目录 -> namespace 映射，
目录下的 .md 文件用单独一行的 --- 分隔知识条目，每条作为一个独立文本入库。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx
import yaml

_SPLIT_RE = re.compile(r"^-{3,}\s*$", re.MULTILINE)

REPO_ROOT = Path(__file__).resolve().parents[1]


def split_entries(markdown: str) -> list[str]:
    return [block.strip() for block in _SPLIT_RE.split(markdown) if block.strip()]


def collect(knowledge_dir: Path, sub_dir: str) -> list[str]:
    target = knowledge_dir / sub_dir
    if not target.is_dir():
        raise SystemExit(f"语料目录不存在：{target}")
    entries: list[str] = []
    for md_file in sorted(target.rglob("*.md")):
        entries.extend(split_entries(md_file.read_text(encoding="utf-8")))
    if not entries:
        raise SystemExit(f"语料目录为空：{target}")
    return entries


def login(client: httpx.Client, account: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"account": account, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True, help="apps-space 下的应用空间目录名")
    # 与 docker-compose 宿主机映射一致（容器内仍是 8000）
    parser.add_argument("--api-base", default="http://127.0.0.1:42867")
    parser.add_argument("--account", default="admin")
    parser.add_argument("--password", default="Admin@123456")
    parser.add_argument("--check", default="", help="索引完成后用该问题做一次检索自检")
    args = parser.parse_args()

    knowledge_dir = REPO_ROOT / "apps-space" / args.slug / "knowledge"
    manifest_path = knowledge_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise SystemExit(f"缺少清单文件：{manifest_path}")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    items = manifest.get("namespaces") or []
    if not items:
        raise SystemExit("manifest.yaml 未声明任何 namespace")

    with httpx.Client(base_url=args.api_base, timeout=300) as client:
        token = login(client, args.account, args.password)
        headers = {"Authorization": f"Bearer {token}"}

        for item in items:
            namespace = item["namespace"]
            entries = collect(knowledge_dir, item["dir"])
            resp = client.post(
                "/api/v1/index",
                headers=headers,
                json={"namespace": namespace, "texts": entries},
            )
            if resp.status_code != 200:
                print(f"[失败] {namespace}: {resp.status_code} {resp.text}")
                return 1
            data = resp.json()
            print(
                f"[完成] {namespace} 条目 {len(entries)} -> "
                f"入库 {data['indexed']} 维度 {data['dimension']}"
            )

        if args.check:
            for item in items:
                resp = client.post(
                    "/api/v1/index/search",
                    headers=headers,
                    json={
                        "namespaces": [item["namespace"]],
                        "query": args.check,
                        "top_k": 2,
                    },
                )
                resp.raise_for_status()
                result = resp.json()
                print(f"\n[检索] {item['namespace']} rerank={result['reranked']}")
                for citation in result["citations"]:
                    preview = citation["content"].replace("\n", " ")[:90]
                    print(f"  {citation['score']:.4f}  {preview}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
