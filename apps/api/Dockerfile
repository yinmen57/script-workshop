FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/api/requirements.txt

COPY packages /app/packages
COPY apps/__init__.py /app/apps/__init__.py
COPY apps/api /app/apps/api
COPY apps/worker /app/apps/worker
# Agent 应用空间与 API 镜像一起发布；本地 compose 可挂载覆盖并以 mtime 热重载
COPY apps-space /app/apps-space
# 剧本业务表迁移
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic

WORKDIR /app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
  CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

# API 默认入口；worker 服务在 compose 中覆盖为 python -m apps.worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/apps/api"]
