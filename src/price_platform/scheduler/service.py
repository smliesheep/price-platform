"""调度核心：30s 到期扫描 + 1s 延时重试提升。

投递语义：先写库（queued + dispatched_at NULL），提交事务后再 XADD；
投递失败的任务由 reaper 通过 `dispatched_at IS NULL` 精确定位并补发。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import asyncpg
from redis.asyncio import Redis

from price_platform.common import metrics as M
from price_platform.common.logging import get_logger
from price_platform.common.queue import (
    MessageFormatError,
    TaskMessage,
    drop_retry,
    due_retries,
    new_trace_id,
    publish,
)
from price_platform.common.settings import Settings
from price_platform.common.timeutil import advance_next_run, utcnow

log = get_logger("scheduler")


@dataclass
class TickStats:
    due: int = 0
    dispatched: int = 0
    duplicates: int = 0
    catchup: int = 0
    publish_errors: int = 0
    new_runs: list[tuple[int, dict[str, Any], datetime]] = field(default_factory=list)


DUE_SQL = """
SELECT t.id AS task_id, t.product_id, t.next_run_at, t.schedule_type,
       t.interval_sec, t.cron_expr, t.priority, s.id AS source_id
FROM tasks t
JOIN products p ON p.id = t.product_id
JOIN sources  s ON s.id = p.source_id
WHERE t.status = 'active'
  AND p.enabled AND s.enabled
  AND t.next_run_at <= now()
ORDER BY t.priority, t.next_run_at
LIMIT $1
FOR UPDATE OF t SKIP LOCKED
"""

ADVANCE_SQL = """
UPDATE tasks
SET next_run_at = $2, last_run_at = $3, updated_at = now()
WHERE id = $1
"""

INSERT_RUN_SQL = """
INSERT INTO task_runs (task_id, product_id, slot_at, attempt, status)
VALUES ($1, $2, $3, 1, 'queued')
ON CONFLICT (task_id, slot_at, attempt) DO NOTHING
RETURNING id
"""


async def tick(
    pool: asyncpg.Pool,
    redis: Redis,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> TickStats:
    now = now or utcnow()
    stats = TickStats()

    async with pool.acquire() as conn, conn.transaction():
        rows = await conn.fetch(DUE_SQL, settings.scheduler_batch)
        stats.due = len(rows)

        for row in rows:
            slot: datetime = row["next_run_at"]
            nxt, missed = advance_next_run(
                schedule_type=row["schedule_type"],
                interval_sec=row["interval_sec"] or 0,
                cron_expr=row["cron_expr"],
                slot=slot,
                now=now,
            )
            if missed:
                stats.catchup += 1
                log.info("slot_skipped", task_id=row["task_id"], missed=missed, slot=slot.isoformat())

            await conn.execute(ADVANCE_SQL, row["task_id"], nxt, slot)

            run_id = await conn.fetchval(
                INSERT_RUN_SQL, row["task_id"], row["product_id"], slot
            )
            if run_id is None:
                stats.duplicates += 1
                continue
            stats.new_runs.append((run_id, dict(row), slot))

    for run_id, row, slot in stats.new_runs:
        msg = TaskMessage(
            run_id=run_id,
            task_id=row["task_id"],
            product_id=row["product_id"],
            source_id=row["source_id"],
            slot_at=slot,
            attempt=1,
            trace_id=new_trace_id(),
            enqueued_at=utcnow(),
        )
        try:
            await publish(redis, settings, msg)
            await pool.execute("UPDATE task_runs SET dispatched_at = now() WHERE id = $1", run_id)
            stats.dispatched += 1
            M.DISPATCH_DELAY.observe(max(0.0, (msg.enqueued_at - slot).total_seconds()))
        except Exception as exc:  # noqa: BLE001 - 单条失败不能影响整批
            stats.publish_errors += 1
            log.error("publish_failed", run_id=run_id, error_msg=str(exc))

    M.SCHEDULER_DUE.set(stats.due)
    M.SCHEDULER_DISPATCHED.inc(stats.dispatched)
    if stats.publish_errors:
        M.SCHEDULER_PUBLISH_ERRORS.inc(stats.publish_errors)
    if stats.catchup:
        M.SCHEDULER_CATCHUP.inc(stats.catchup)
    M.SCHEDULER_TICK.labels("ok").inc()

    if stats.due or stats.dispatched:
        log.info(
            "scheduler_tick",
            due=stats.due,
            dispatched=stats.dispatched,
            duplicated=stats.duplicates,
            catchup=stats.catchup,
            publish_errors=stats.publish_errors,
        )
    return stats


PROMOTE_INSERT = """
INSERT INTO task_runs (task_id, product_id, slot_at, attempt, status)
VALUES ($1, $2, $3, $4, 'queued')
ON CONFLICT (task_id, slot_at, attempt) DO NOTHING
RETURNING id
"""

TASK_STATE = """
SELECT t.status, p.enabled AS product_enabled, s.enabled AS source_enabled
FROM tasks t
JOIN products p ON p.id = t.product_id
JOIN sources  s ON s.id = p.source_id
WHERE t.id = $1
"""


async def promote_due_retries(pool: asyncpg.Pool, redis: Redis, settings: Settings) -> int:
    """把 ZSET 里到期的"下一次尝试"提升为 queued 并投递。"""
    members = await due_retries(redis, settings)
    promoted = 0

    for raw in members:
        try:
            msg = TaskMessage.from_json(raw)
        except MessageFormatError as exc:
            log.warning("retry_message_invalid", error_msg=str(exc))
            await drop_retry(redis, settings, raw)
            continue

        state = await pool.fetchrow(TASK_STATE, msg.task_id)
        if state is None or state["status"] != "active" or not state["product_enabled"] or not state["source_enabled"]:
            await pool.execute(
                "UPDATE task_runs SET status='canceled', finished_at=now() WHERE id=$1 AND status='retry_wait'",
                msg.run_id,
            )
            await drop_retry(redis, settings, raw)
            log.info("retry_canceled", run_id=msg.run_id, task_id=msg.task_id)
            continue

        new_run_id = await pool.fetchval(
            PROMOTE_INSERT, msg.task_id, msg.product_id, msg.slot_at, msg.attempt + 1
        )
        if new_run_id is not None:
            new_msg = msg.next_attempt(new_run_id)
            try:
                await publish(redis, settings, new_msg)
                promoted += 1
            except Exception as exc:  # noqa: BLE001
                log.error("retry_publish_failed", run_id=new_run_id, error_msg=str(exc))
        await drop_retry(redis, settings, raw)

    if promoted:
        M.RETRY_PROMOTED.inc(promoted)
        log.info("retry_promoted", count=promoted)
    M.RETRY_QUEUE.set(await redis.zcard(settings.retry_zset))
    return promoted


async def clock_ms(redis: Redis) -> int:
    """调试用：Redis 视角的毫秒时间戳。"""
    seconds, micros = await redis.time()
    return int(seconds) * 1000 + int(micros) // 1000


def monotonic_ms() -> int:
    return int(time.time() * 1000)
