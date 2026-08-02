FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Debian 国内源 + PyPI 清华源，避免构建卡在官方源
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /app/apps/api/requirements.txt
# 国内 PyPI 镜像，避免 Docker Hub/官方源过慢
RUN pip install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    -r /app/apps/api/requirements.txt

COPY packages /app/packages
COPY apps/__init__.py /app/apps/__init__.py
COPY apps/api /app/apps/api
# 剧本业务表迁移
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic

WORKDIR /app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=10 \
  CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

# API 默认入口；Celery worker/beat 在 compose 中覆盖 command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/apps/api"]
