"""reaper：孤儿回收、丢消息补投、僵尸重试修复、队列水位。

所有动作都是条件 UPDATE，重复执行无副作用。
"""

from __future__ import annotations

import asyncpg
from redis.asyncio import Redis

from price_platform.common import metrics as M
from price_platform.common.logging import get_logger
from price_platform.common.queue import (
    TaskMessage,
    new_trace_id,
    publish,
    queue_stats,
    schedule_retry,
)
from price_platform.common.settings import Settings
from price_platform.common.timeutil import utcnow

log = get_logger("reaper")

ORPHAN_SQL = """
WITH orphans AS (
    SELECT r.id, r.task_id, r.product_id, r.slot_at, r.attempt, r.trace_id,
           t.max_retry, s.id AS source_id
    FROM task_runs r
    JOIN tasks t    ON t.id = r.task_id
    JOIN products p ON p.id = r.product_id
    JOIN sources s  ON s.id = p.source_id
    LEFT JOIN workers w ON w.id = r.worker_id
    WHERE r.status = 'running'
      AND (
            r.started_at < now() - make_interval(secs => t.timeout_sec + $1)
         OR w.last_heartbeat < now() - make_interval(secs => $2)
      )
    LIMIT 100
    FOR UPDATE OF r SKIP LOCKED
)
UPDATE task_runs r
SET status = CASE WHEN o.attempt < o.max_retry THEN 'retry_wait' ELSE 'timeout' END,
    error_type = 'timeout',
    error_msg = 'orphaned: worker lost or exceeded timeout',
    finished_at = now(),
    duration_ms = (EXTRACT(EPOCH FROM (now() - r.started_at)) * 1000)::int
FROM orphans o
WHERE r.id = o.id
RETURNING r.id, r.task_id, r.product_id, r.slot_at, r.attempt, r.status,
          o.source_id, o.max_retry, o.trace_id
"""

UNDISPATCHED_SQL = """
SELECT r.id, r.task_id, r.product_id, r.slot_at, r.attempt, s.id AS source_id
FROM task_runs r
JOIN products p ON p.id = r.product_id
JOIN sources s  ON s.id = p.source_id
WHERE r.status = 'queued'
  AND r.dispatched_at IS NULL
  AND r.queued_at < now() - make_interval(secs => $1)
ORDER BY r.id
LIMIT 200
"""

STALE_RETRY_SQL = """
SELECT r.id, r.task_id, r.product_id, r.slot_at, r.attempt, r.trace_id, s.id AS source_id
FROM task_runs r
JOIN products p ON p.id = r.product_id
JOIN sources s  ON s.id = p.source_id
WHERE r.status = 'retry_wait'
  AND r.finished_at < now() - make_interval(secs => $1)
ORDER BY r.id
LIMIT 100
"""


async def reap_orphans(pool: asyncpg.Pool, redis: Redis, settings: Settings) -> int:
    rows = await pool.fetch(
        ORPHAN_SQL,
        settings.orphan_grace_sec,
        settings.worker_heartbeat_timeout_sec,
    )
    for row in rows:
        msg = TaskMessage(
            run_id=row["id"],
            task_id=row["task_id"],
            product_id=row["product_id"],
            source_id=row["source_id"],
            slot_at=row["slot_at"],
            attempt=int(row["attempt"]),
            trace_id=row["trace_id"] or new_trace_id(),
            enqueued_at=utcnow(),
        )
        if row["status"] == "retry_wait":
            await schedule_retry(redis, settings, msg, settings.retry_delay_sec)
            M.REAPER_REAPED.labels("orphan_retry").inc()
            log.warning("reaper_orphan", run_id=msg.run_id, action="retry")
        else:
            await redis.xadd(
                settings.queue_dlq,
                {
                    **msg.to_fields(),
                    "error_type": "timeout",
                    "error_msg": "orphaned",
                    "failed_at": utcnow().isoformat(),
                    "total_attempts": str(row["attempt"]),
                },
                maxlen=10_000,
                approximate=True,
            )
            M.REAPER_REAPED.labels("orphan_timeout").inc()
            log.error("reaper_orphan", run_id=msg.run_id, action="dlq")
    return len(rows)


async def reconcile_undispatched(pool: asyncpg.Pool, redis: Redis, settings: Settings) -> int:
    rows = await pool.fetch(UNDISPATCHED_SQL, settings.stale_queued_sec)
    for row in rows:
        msg = TaskMessage(
            run_id=row["id"],
            task_id=row["task_id"],
            product_id=row["product_id"],
            source_id=row["source_id"],
            slot_at=row["slot_at"],
            attempt=int(row["attempt"]),
            trace_id=new_trace_id(),
            enqueued_at=utcnow(),
        )
        try:
            await publish(redis, settings, msg)
            await pool.execute("UPDATE task_runs SET dispatched_at = now() WHERE id = $1", msg.run_id)
            M.REAPER_REAPED.labels("undispatched").inc()
            log.info("reaper_undispatched", run_id=msg.run_id)
        except Exception as exc:  # noqa: BLE001
            log.error("reaper_publish_failed", run_id=msg.run_id, error_msg=str(exc))
    return len(rows)


async def repair_stale_retry_wait(pool: asyncpg.Pool, redis: Redis, settings: Settings) -> int:
    rows = await pool.fetch(STALE_RETRY_SQL, settings.stale_retry_wait_sec)
    for row in rows:
        msg = TaskMessage(
            run_id=row["id"],
            task_id=row["task_id"],
            product_id=row["product_id"],
            source_id=row["source_id"],
            slot_at=row["slot_at"],
            attempt=int(row["attempt"]),
            trace_id=row["trace_id"] or new_trace_id(),
            enqueued_at=utcnow(),
        )
        await schedule_retry(redis, settings, msg, 0)
        M.REAPER_REAPED.labels("stale_retry").inc()
        log.warning("reaper_stale_retry", run_id=msg.run_id)
    return len(rows)


async def refresh_queue_metrics(redis: Redis, settings: Settings) -> None:
    stats = await queue_stats(redis, settings)
    M.QUEUE_LAG.labels(settings.queue_stream).set(stats.lag)
    M.QUEUE_PENDING.labels(settings.queue_stream, settings.queue_group).set(stats.pending)
    M.QUEUE_DLQ.set(stats.dlq)
    M.RETRY_QUEUE.set(stats.retry_zset)


async def run_once(pool: asyncpg.Pool, redis: Redis, settings: Settings) -> dict[str, int]:
    orphans = await reap_orphans(pool, redis, settings)
    undispatched = await reconcile_undispatched(pool, redis, settings)
    stale = await repair_stale_retry_wait(pool, redis, settings)
    await refresh_queue_metrics(redis, settings)
    if orphans or undispatched or stale:
        log.info("reaper_tick", orphans=orphans, undispatched=undispatched, stale_retry=stale)
    return {"orphans": orphans, "undispatched": undispatched, "stale_retry": stale}
