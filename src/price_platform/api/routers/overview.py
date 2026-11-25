"""概览指标：一次聚合查询 + 队列水位。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from price_platform.api.deps import CurrentUser, SessionDep
from price_platform.api.schemas.common import ok
from price_platform.common.queue import queue_stats
from price_platform.common.settings import settings
from price_platform.common.timeutil import utcnow

router = APIRouter(tags=["overview"])

OVERVIEW_SQL = text(
    """
    SELECT
      (SELECT count(*) FROM price_records WHERE collected_at >= now() - interval '24 hours') AS prices_24h,
      (SELECT count(*) FROM task_runs WHERE queued_at >= now() - interval '24 hours')        AS runs_24h,
      (SELECT count(*) FROM task_runs
        WHERE queued_at >= now() - interval '24 hours' AND status = 'success')               AS success_24h,
      (SELECT count(*) FROM products WHERE enabled)                                          AS products_enabled,
      (SELECT count(*) FROM products)                                                        AS products_total,
      (SELECT count(*) FROM task_runs WHERE status IN ('queued','running'))                  AS inflight,
      (SELECT count(*) FROM workers
        WHERE last_heartbeat > now() - make_interval(secs => :hb))                            AS workers_online
    """
)

TOP_ERRORS_SQL = text(
    """
    SELECT error_type, count(*) AS cnt
    FROM task_runs
    WHERE status IN ('failed','timeout')
      AND finished_at >= now() - interval '24 hours'
      AND error_type IS NOT NULL
    GROUP BY error_type
    ORDER BY cnt DESC
    LIMIT 5
    """
)


@router.get("/overview")
async def overview(session: SessionDep, request: Request, user: CurrentUser) -> dict:
    del user
    row = (
        await session.execute(OVERVIEW_SQL, {"hb": settings.worker_heartbeat_timeout_sec})
    ).mappings().one()
    errors = (await session.execute(TOP_ERRORS_SQL)).mappings().all()
    stats = await queue_stats(request.app.state.redis, settings)

    runs_24h = int(row["runs_24h"] or 0)
    success_24h = int(row["success_24h"] or 0)
    return ok(
        {
            "prices_24h": int(row["prices_24h"] or 0),
            "runs_24h": runs_24h,
            "success_24h": success_24h,
            "success_rate": round(success_24h / runs_24h, 4) if runs_24h else 0.0,
            "products_enabled": int(row["products_enabled"] or 0),
            "products_total": int(row["products_total"] or 0),
            "inflight": int(row["inflight"] or 0),
            "workers_online": int(row["workers_online"] or 0),
            "queue": {
                "length": stats.length,
                "pending": stats.pending,
                "lag": stats.lag,
                "dlq": stats.dlq,
                "retry_zset": stats.retry_zset,
            },
            "top_errors": [{"error_type": e["error_type"], "count": int(e["cnt"])} for e in errors],
            "generated_at": utcnow().isoformat(),
        }
    )
