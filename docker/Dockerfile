# syntax=docker/dockerfile:1

# ---------- 公共基础：依赖 + 代码 ----------
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai
WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN pip install --upgrade pip && pip install .

# ---------- API：不装 Playwright，镜像小 ----------
FROM base AS api
RUN useradd --uid 10001 --create-home appuser
USER 10001
EXPOSE 8000
CMD ["python", "-m", "price_platform.api.main"]

# ---------- Worker：官方 Playwright 镜像，自带 Chromium ----------
FROM mcr.microsoft.com/playwright/python:v1.65.2-jammy AS worker
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai
WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN pip install --upgrade pip \
    && pip install "playwright==1.65.2" . \
    && python -c "import price_platform, playwright; print('worker image ok')"
USER 10001
EXPOSE 9100
CMD ["python", "-m", "price_platform.worker.main"]

