"""进程级配置：全部来自环境变量（PP_ 前缀）/ .env。"""

from __future__ import annotations

import socket
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 基础
    log_level: str = "INFO"
    tz: str = "Asia/Shanghai"
    pod_name: str = ""
    node_name: str = ""

    # 依赖
    database_url: str = "postgresql://price:price@localhost:5432/price"
    redis_url: str = "redis://localhost:6379/0"

    # 队列
    queue_stream: str = "price:tasks"
    queue_group: str = "workers"
    queue_dlq: str = "price:tasks:dlq"
    retry_zset: str = "price:retry"

    # scheduler
    scheduler_tick_sec: int = 30
    scheduler_batch: int = 200
    promote_interval_sec: int = 1

    # worker
    worker_concurrency: int = 2
    worker_timeout_sec: int = 300
    worker_max_retry: int = 3
    retry_delay_sec: int = 5
    worker_heartbeat_sec: int = 15
    browser_headless: bool = True
    browser_channel: str = ""          # 本地开发可用 msedge，容器内留空走内置 chromium
    selector_dir: str = "./configs/selectors"
    mock_shop_url: str = "http://localhost:8080"

    # reaper
    reaper_interval_sec: int = 15
    orphan_grace_sec: int = 30
    stale_queued_sec: int = 30
    stale_retry_wait_sec: int = 60
    worker_heartbeat_timeout_sec: int = 90

    # api
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_min: int = 720
    admin_username: str = "admin"
    admin_password_hash: str = ""
    disable_auth: bool = False
    cors_origins: str = "*"

    # metrics
    metrics_port: int = 9100

    @property
    def pod(self) -> str:
        return self.pod_name or socket.gethostname()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

