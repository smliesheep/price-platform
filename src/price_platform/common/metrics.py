"""Prometheus 指标定义 + 非 API 组件的管理端口（/metrics、/-/healthy、/readyz）。"""

from __future__ import annotations

from typing import Awaitable, Callable

from aiohttp import web
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ---- scheduler ----
SCHEDULER_TICK = Counter("price_scheduler_tick_total", "scheduler tick count", ["result"])
SCHEDULER_DUE = Gauge("price_scheduler_due_tasks", "due tasks in last tick")
SCHEDULER_DISPATCHED = Counter("price_scheduler_dispatched_total", "tasks published to stream")
SCHEDULER_PUBLISH_ERRORS = Counter("price_scheduler_publish_errors_total", "publish failures")
SCHEDULER_CATCHUP = Counter("price_scheduler_catchup_skipped_total", "skipped slots after downtime")
DISPATCH_DELAY = Histogram(
    "price_scheduler_dispatch_delay_seconds",
    "delay between slot_at and enqueue",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 300),
)
RETRY_PROMOTED = Counter("price_retry_promoted_total", "retries moved back to stream")
RETRY_QUEUE = Gauge("price_retry_queue_length", "items waiting in retry zset")

# ---- queue ----
QUEUE_LAG = Gauge("price_queue_lag", "consumer group lag", ["stream"])
QUEUE_PENDING = Gauge("price_queue_pending", "pending entries (PEL)", ["stream", "group"])
QUEUE_DLQ = Gauge("price_queue_dlq_length", "dead letter stream length")

# ---- worker ----
TASKS_STARTED = Counter("price_worker_tasks_started_total", "tasks started")
TASKS_FINISHED = Counter("price_worker_tasks_finished_total", "tasks finished", ["status"])
TASK_DURATION = Histogram(
    "price_worker_task_duration_seconds",
    "task duration",
    buckets=(0.5, 1, 2, 3, 5, 10, 30, 60, 120, 300),
)
INFLIGHT = Gauge("price_worker_inflight", "in-flight tasks", ["pod"])
BROWSER_RESTARTS = Counter("price_worker_browser_restarts_total", "browser restarts")
RUN_CLAIMS = Counter("price_run_claims_total", "claim results", ["result"])

# ---- reaper ----
REAPER_REAPED = Counter("price_reaper_reaped_total", "reaped runs", ["reason"])

# ---- api（由 prometheus-fastapi-instrumentator 之外的手写中间件维护）----
HTTP_REQUESTS = Counter("price_http_requests_total", "http requests", ["method", "path", "status"])
HTTP_DURATION = Histogram(
    "price_http_request_duration_seconds",
    "http duration",
    ["path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2),
)


async def start_admin_server(
    port: int,
    ready_check: Callable[[], Awaitable[None]] | None = None,
) -> web.AppRunner:
    async def metrics(_: web.Request) -> web.Response:
        return web.Response(body=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})

    async def healthy(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def readyz(_: web.Request) -> web.Response:
        if ready_check is None:
            return web.Response(text="ok")
        try:
            await ready_check()
        except Exception as exc:  # noqa: BLE001 - readiness 只关心结果
            return web.Response(status=503, text=f"not ready: {exc}")
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/metrics", metrics)
    app.router.add_get("/-/healthy", healthy)
    app.router.add_get("/readyz", readyz)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    return runner
