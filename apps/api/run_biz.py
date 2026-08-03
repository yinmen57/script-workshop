"""本地启动业务 API。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import uvicorn

from framework.infra.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.biz_main:app",
        host=settings.app_host,
        port=settings.biz_app_port,
        reload=settings.app_debug,
        app_dir=str(API_DIR),
    )


if __name__ == "__main__":
    main()
