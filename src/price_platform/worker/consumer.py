"""Worker 消费主循环：抢占 → 抓取 → 落库 → ack；失败按策略重试或进 DLQ。"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import asyncpg
from redis.asyncio import Redis

from price_platform.common import metrics as M
from price_platform.common.errors import ErrorType, classify, decide
from price_platform.common.logging import get_logger, trace_id_var
from price_platform.common.queue import (
    MessageFormatError,
    TaskMessage,
    schedule_retry,
)
from price_platform.common.settings import Settings
from price_platform.common.timeutil import utcnow
from price_platform.worker.adapters.base import BaseAdapter, PriceSnapshot
from price_platform.worker.browser import BrowserManager
from price_platform.worker.ratelimit import RateLimiter
from price_platform.worker.selectors import SelectorSet, SelectorStore

log = get_logger("worker")

CLAIM_SQL = """
UPDATE task_runs
SET status = 'running', worker_id = $2, started_at = now(), trace_id = $3
WHERE id = $1 AND status = 'queued'
RETURNING task_id, product_id, slot_at, attempt
"""

CONTEXT_SQL = """
SELECT p.id AS product_id, p.title, p.url, p.selector_version, p.external_id,
       p.enabled AS product_enabled,
       s.id AS source_id, s.adapter, s.base_url, s.rate_limit_per_min,
       s.enabled AS source_enabled,
       t.id AS task_id, t.timeout_sec, t.max_retry, t.status AS task_status
FROM products p
JOIN sources s ON s.id = p.source_id
LEFT JOIN tasks t ON t.product_id = p.id
WHERE p.id = $1
"""

SAVE_PRICE_SQL = """
INSERT INTO price_records (product_id, run_id, price, currency, in_stock, collected_at, raw)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (product_id, collected_at) DO NOTHING
"""

UPDATE_PRODUCT_SQL = """
UPDATE products
SET current_price = $2, last_collected_at = $3, last_status = 'success', updated_at = now()
WHERE id = $1 AND (last_collected_at IS NULL OR last_collected_at <= $3)
"""

UPDATE_RUN_SUCCESS = """
UPDATE task_runs
SET status = 'success', finished_at = now(), duration_ms = $2, http_status = $3
WHERE id = $1 AND status = 'running'
"""

UPDATE_RUN_FAILURE = """
UPDATE task_runs
SET status = $2, error_type = $3, error_msg = $4, http_status = $5,
    finished_at = now(), duration_ms = $6
WHERE id = $1 AND status = 'running'
"""

HEARTBEAT_SQL = """
INSERT INTO workers (id, node, version, started_at, last_heartbeat, inflight)
VALUES ($1, $2, $3, now(), now(), $4)
ON CONFLICT (id) DO UPDATE
SET node = EXCLUDED.node, version = EXCLUDED.version,
    last_heartbeat = now(), inflight = EXCLUDED.inflight
"""


@dataclass
class WorkerContext:
    settings: Settings
    pool: asyncpg.Pool
    redis: Redis
    browser: BrowserManager
    adapters: dict[str, BaseAdapter]
    selectors: SelectorStore
    limiter: RateLimiter
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    inflight: int = 0
    stopping: bool = False
    cache_ttl: float = 30.0
    _cache: dict[int, tuple[float, dict[str, Any] | None]] = field(default_factory=dict)

    async def load_context(self, product_id: int) -> dict[str, Any]:
        now = time.monotonic()
        cached = self._cache.get(product_id)
        if cached and now - cached[0] < self.cache_ttl:
            if cached[1] is None:
                raise LookupError(f"product {product_id} not found")
            return cached[1]
        row = await self.pool.fetchrow(CONTEXT_SQL, product_id)
        data = dict(row) if row else None
        self._cache[product_id] = (now, data)
        if data is None:
            raise LookupError(f"product {product_id} not found")
        return data


async def _ack(ctx: WorkerContext, msg_id: str) -> None:
    await ctx.redis.xack(ctx.settings.queue_stream, ctx.settings.queue_group, msg_id)


async def handle(ctx: WorkerContext, msg_id: str, fields: dict[str, str]) -> None:
    try:
        msg = TaskMessage.from_fields(fields)
    except MessageFormatError as exc:
        await _ack(ctx, msg_id)
        await ctx.redis.xadd(
            ctx.settings.queue_dlq,
            {"raw": json.dumps(fields, ensure_ascii=False), "error": str(exc)},
            maxlen=10_000,
            approximate=True,
        )
        log.error("poison_message", error_msg=str(exc))
        return

    trace_id_var.set(msg.trace_id)
    claimed = await ctx.pool.fetchrow(CLAIM_SQL, msg.run_id, ctx.settings.pod, msg.trace_id)
    if claimed is None:
        await _ack(ctx, msg_id)
        M.RUN_CLAIMS.labels("duplicate").inc()
        return
    M.RUN_CLAIMS.labels("ok").inc()

    attempt = int(claimed["attempt"])
    started = time.monotonic()
    ctx.inflight += 1
    M.TASKS_STARTED.inc()
    M.INFLIGHT.labels(ctx.settings.pod).set(ctx.inflight)

    try:
        data = await ctx.load_context(msg.product_id)
        if (
            not data.get("product_enabled")
            or not data.get("source_enabled")
            or data.get("task_status") != "active"
        ):
            await _finish_canceled(ctx, msg)
            return

        selectors: SelectorSet = ctx.selectors.get(data["adapter"], data["selector_version"])
        timeout = int(data.get("timeout_sec") or ctx.settings.worker_timeout_sec)
        adapter = ctx.adapters.get(data["adapter"]) or ctx.adapters["generic"]

        await ctx.limiter.acquire(int(data["source_id"]), int(data["rate_limit_per_min"] or 0))
        browser = await ctx.browser.ensure()
        product_ctx = {"url": data["url"]}
        source_ctx = {"base_url": data["base_url"]}
        snapshot = await asyncio.wait_for(
            adapter.collect(browser, product_ctx, source_ctx, selectors),
            timeout=timeout,
        )
        await _save_success(ctx, msg, snapshot, started)
    except Exception as exc:  # noqa: BLE001 - 任何失败都必须收尾，否则 ack 后任务永久 running
        await _handle_failure(ctx, msg, exc, attempt, started)
    finally:
        ctx.inflight -= 1
        M.INFLIGHT.labels(ctx.settings.pod).set(ctx.inflight)
        M.TASK_DURATION.observe(time.monotonic() - started)
        await _ack(ctx, msg_id)


async def _save_success(
    ctx: WorkerContext, msg: TaskMessage, snapshot: PriceSnapshot, started: float
) -> None:
    duration_ms = int((time.monotonic() - started) * 1000)
    async with ctx.pool.acquire() as conn, conn.transaction():
        await conn.execute(
            SAVE_PRICE_SQL,
            msg.product_id,
            msg.run_id,
            snapshot.price,
            snapshot.currency,
            snapshot.in_stock,
            msg.slot_at,
            json.dumps(snapshot.raw, ensure_ascii=False),
        )
        await conn.execute(UPDATE_PRODUCT_SQL, msg.product_id, snapshot.price, msg.slot_at)
        result = await conn.execute(UPDATE_RUN_SUCCESS, msg.run_id, duration_ms, snapshot.http_status)
    if result.endswith("0"):
        log.warning("run_already_final", run_id=msg.run_id)
        return
    M.TASKS_FINISHED.labels("success").inc()
    log.info(
        "task_success",
        run_id=msg.run_id,
        task_id=msg.task_id,
        product_id=msg.product_id,
        attempt=msg.attempt,
        duration_ms=duration_ms,
        http_status=snapshot.http_status,
    )


async def _finish_canceled(ctx: WorkerContext, msg: TaskMessage) -> None:
    await ctx.pool.execute(
        UPDATE_RUN_FAILURE,
        msg.run_id,
        "canceled",
        "disabled",
        "product/source/task disabled",
        None,
        0,
    )
    M.TASKS_FINISHED.labels("canceled").inc()
    log.info("task_canceled", run_id=msg.run_id, product_id=msg.product_id)


async def _handle_failure(
    ctx: WorkerContext,
    msg: TaskMessage,
    exc: BaseException,
    attempt: int,
    started: float,
) -> None:
    error_type: ErrorType = classify(exc)
    max_retry = ctx.settings.worker_max_retry
    try:
        data = await ctx.load_context(msg.product_id)
        max_retry = int(data.get("max_retry") or ctx.settings.worker_max_retry)
    except LookupError:
        pass

    decision = decide(error_type, attempt, max_retry)
    duration_ms = int((time.monotonic() - started) * 1000)
    http_status = getattr(exc, "http_status", None)

    updated = await ctx.pool.execute(
        UPDATE_RUN_FAILURE,
        msg.run_id,
        decision.status,
        error_type.value,
        str(exc)[:2000],
        http_status,
        duration_ms,
    )
    if updated.endswith("0"):
        log.warning("run_already_final", run_id=msg.run_id)
        return

    M.TASKS_FINISHED.labels(decision.status).inc()

    if decision.retry:
        retry_msg = TaskMessage(
            run_id=msg.run_id,
            task_id=msg.task_id,
            product_id=msg.product_id,
            source_id=msg.source_id,
            slot_at=msg.slot_at,
            attempt=attempt,
            trace_id=msg.trace_id,
            enqueued_at=msg.enqueued_at,
        )
        await schedule_retry(ctx.redis, ctx.settings, retry_msg, ctx.settings.retry_delay_sec)
        log.warning(
            "task_retry_scheduled",
            run_id=msg.run_id,
            task_id=msg.task_id,
            attempt=attempt,
            error_type=error_type.value,
            duration_ms=duration_ms,
            msg=f"retry in {ctx.settings.retry_delay_sec}s",
        )
        return

    await ctx.redis.xadd(
        ctx.settings.queue_dlq,
        {
            **msg.to_fields(),
            "error_type": error_type.value,
            "error_msg": str(exc)[:1000],
            "failed_at": utcnow().isoformat(),
            "total_attempts": str(attempt),
        },
        maxlen=10_000,
        approximate=True,
    )
    M.QUEUE_DLQ.set(int(await ctx.redis.xlen(ctx.settings.queue_dlq)))

    if error_type is ErrorType.NOT_FOUND:
        await ctx.pool.execute(
            "UPDATE products SET enabled = false, last_status = 'not_found', updated_at = now() WHERE id = $1",
            msg.product_id,
        )
        await ctx.pool.execute(
            "INSERT INTO alerts (product_id, rule, level, payload) VALUES ($1, 'not_found', 'warn', $2)",
            msg.product_id,
            json.dumps({"error_msg": str(exc)[:500]}, ensure_ascii=False),
        )

    log.error(
        "task_failed",
        run_id=msg.run_id,
        task_id=msg.task_id,
        product_id=msg.product_id,
        attempt=attempt,
        error_type=error_type.value,
        error_msg=str(exc)[:500],
        duration_ms=duration_ms,
    )


async def consume_loop(ctx: WorkerContext, slot: int) -> None:
    del slot
    settings = ctx.settings
    while not ctx.stopping:
        try:
            claimed = await ctx.redis.xautoclaim(
                settings.queue_stream,
                settings.queue_group,
                settings.pod,
                min_idle_time=60_000,
                start_id="0-0",
                count=10,
            )
            entries = claimed[1] if claimed else []
            for msg_id, fields in entries:
                try:
                    await handle(ctx, msg_id, fields)
                except Exception:
                    log.exception("handle_failed", msg_id=msg_id)
        except Exception as exc:  # noqa: BLE001 - PEL 接管失败不致命
            log.warning("xautoclaim_failed", error_msg=str(exc))

        try:
            resp = await ctx.redis.xreadgroup(
                settings.queue_group,
                settings.pod,
                {settings.queue_stream: ">"},
                count=1,
                block=2000,
            )
        except Exception as exc:  # noqa: BLE001 - Redis 抖动时退避
            log.warning("xreadgroup_failed", error_msg=str(exc))
            await asyncio.sleep(2)
            continue

        if not resp:
            continue
        for _stream, entries in resp:
            for msg_id, fields in entries:
                if ctx.stopping:
                    break
                try:
                    await handle(ctx, msg_id, fields)
                except Exception:
                    log.exception("handle_failed", msg_id=msg_id)


async def heartbeat_loop(ctx: WorkerContext, version: str) -> None:
    while not ctx.stopping:
        try:
            await ctx.pool.execute(
                HEARTBEAT_SQL, ctx.settings.pod, ctx.settings.node_name, version, ctx.inflight
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("heartbeat_failed", error_msg=str(exc))
        try:
            await asyncio.wait_for(ctx.stop_event.wait(), timeout=ctx.settings.worker_heartbeat_sec)
        except asyncio.TimeoutError:
            pass


