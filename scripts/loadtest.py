"""压测：绕过调度器，按目标速率直接投递任务，观察队列 lag 与吞吐。

用法：
    python scripts/loadtest.py --total 3000 --rate 0.5 --fail-rate 0.1
    python scripts/loadtest.py --total 10000 --rate 2

说明：
- 直接 INSERT task_runs + XADD，避免把 PG 行锁变成瓶颈；
- 每个任务使用唯一的 slot_at（微秒级偏移），避免唯一键冲突；
- 结束时打印任务状态分布与 Redis 队列水位。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import timedelta
from pathlib import Path

import asyncpg
from redis.asyncio import Redis

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from price_platform.common.queue import TaskMessage, publish, queue_stats  # noqa: E402
from price_platform.common.settings import settings  # noqa: E402
from price_platform.common.timeutil import utcnow  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", type=int, default=1000)
    parser.add_argument("--rate", type=float, default=1.0, help="每秒投入任务数")
    parser.add_argument("--fail-rate", type=float, default=0.0, help="把 Mock 商城的失败注入打开")
    parser.add_argument("--mock-url", default="http://127.0.0.1:18088")
    parser.add_argument("--wait", action="store_true", help="投递后等待队列排空")
    args = parser.parse_args()

    pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=2, max_size=5)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    products = await pool.fetch(
        """
        SELECT p.id AS product_id, p.source_id, t.id AS task_id
        FROM products p JOIN tasks t ON t.product_id = p.id
        WHERE p.enabled AND t.status = 'active'
        ORDER BY p.id
        """
    )
    if not products:
        print("no enabled products")
        return 1

    if args.fail_rate > 0:
        import httpx

        try:
            httpx.post(f"{args.mock_url}/admin/config", json={"fail_rate": args.fail_rate}, timeout=5)
            print(f"mock-shop fail_rate={args.fail_rate}")
        except Exception as exc:  # noqa: BLE001
            print(f"warn: cannot set mock fail rate: {exc}")

    started = time.perf_counter()
    sent = 0
    interval = 1.0 / args.rate if args.rate > 0 else 0
    for i in range(args.total):
        product = products[i % len(products)]
        slot = utcnow() + timedelta(microseconds=i)
        run_id = await pool.fetchval(
            """
            INSERT INTO task_runs (task_id, product_id, slot_at, attempt, status)
            VALUES ($1, $2, $3, 1, 'queued')
            RETURNING id
            """,
            product["task_id"],
            product["product_id"],
            slot,
        )
        msg = TaskMessage(
            run_id=run_id,
            task_id=product["task_id"],
            product_id=product["product_id"],
            source_id=product["source_id"],
            slot_at=slot,
            attempt=1,
            trace_id=f"load{i:08d}",
            enqueued_at=utcnow(),
        )
        await publish(redis, settings, msg)
        await pool.execute("UPDATE task_runs SET dispatched_at = now() WHERE id = $1", run_id)
        sent += 1
        if sent % 200 == 0:
            elapsed = time.perf_counter() - started
            print(f"  sent={sent} elapsed={elapsed:.1f}s rate={sent / elapsed:.2f}/s")
        if interval:
            target = started + sent * interval
            delay = target - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)

    elapsed = time.perf_counter() - started
    print(f"submitted {sent} tasks in {elapsed:.1f}s ({sent / elapsed:.2f} tasks/s)")

    if args.wait:
        print("waiting for queue to drain...")
        deadline = time.time() + 1800
        while time.time() < deadline:
            stats = await queue_stats(redis, settings)
            if stats.lag == 0 and stats.pending == 0:
                break
            await asyncio.sleep(2)
            print(f"  queue len={stats.length} lag={stats.lag} pending={stats.pending}")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT status, count(*) AS c
            FROM task_runs
            WHERE trace_id LIKE 'load%'
            GROUP BY status ORDER BY c DESC
            """
        )
    for row in rows:
        print(f"  {row['status']:<10} {row['c']}")

    overflow = await pool.fetchval("SELECT count(*) FROM task_runs WHERE trace_id LIKE 'load%' AND status = 'queued'")
    print(f"remaining queued: {overflow}")

    await redis.aclose()
    await pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

