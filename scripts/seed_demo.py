"""回填 demo-4d 演示数据集（3824 条价格记录 / 5456 条执行记录）。

算法（对应设计文档 §7.5）：
  计划执行 3840 = 20 商品 × 48 次/天 × 4 天
  下架终止   16 = 2 商品 × 8 槽位（not_found，不重试）
  成功执行 3824 = 3840 - 16                  → 3824 条 price_records
  抖动失败 1616 = 1152 槽位失败 1 次 + 232 槽位失败 2 次
  执行记录 5456 = 3824 成功 + 1616 抖动失败 + 16 下架失败

用法：
    python scripts/seed_demo.py --days 4 --products 20 --interval 1800 --reset
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from price_platform.common.settings import settings  # noqa: E402

UTC = timezone.utc


def align_start(now: datetime, days: int, interval: int) -> datetime:
    start = (now - timedelta(days=days)).replace(second=0, microsecond=0)
    step_min = max(1, interval // 60)
    return start.replace(minute=(start.minute // step_min) * step_min)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=4)
    parser.add_argument("--products", type=int, default=20)
    parser.add_argument("--interval", type=int, default=1800)
    parser.add_argument("--seed", type=int, default=20261125)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    random.seed(args.seed)
    slots_per_day = max(1, 86400 // args.interval)
    total_planned = args.products * slots_per_day * args.days

    # 只有 4 天 × 20 商品 × 48 槽位时才严格对齐 3824/5456；其余规模按同比例缩放
    scale = total_planned / 3840
    not_found_slots = max(2, round(16 * scale))
    success_slots = total_planned - not_found_slots
    flaky_once = max(1, round(1152 * scale))
    flaky_twice = max(0, round(232 * scale))
    flaky_slots = flaky_once + flaky_twice
    failed_attempts = flaky_once + 2 * flaky_twice
    expected_runs = success_slots + failed_attempts + not_found_slots

    pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=2, max_size=5)
    async with pool.acquire() as conn:
        products = await conn.fetch(
            """
            SELECT p.id AS product_id, t.id AS task_id, p.title
            FROM products p JOIN tasks t ON t.product_id = p.id
            ORDER BY p.id LIMIT $1
            """,
            args.products,
        )
        if not products:
            print("no products found; run scripts/seed.py first")
            return 1

        if args.reset:
            await conn.execute("TRUNCATE task_runs, price_records RESTART IDENTITY")

        start = align_start(datetime.now(tz=UTC), args.days, args.interval)

        # 下架：前两个商品的最后 8 个槽位
        down_keys = {(products[0]["product_id"], i) for i in range(total_planned // args.products - 8, total_planned // args.products)}
        down_keys |= {(products[1]["product_id"], i) for i in range(total_planned // args.products - 8, total_planned // args.products)}
        candidates = [
            (p["product_id"], s) for p in products for s in range(slots_per_day * args.days)
        ]
        healthy = [key for key in candidates if key not in down_keys]
        flaky_keys = random.sample(healthy, min(flaky_slots, len(healthy)))
        flaky = {key: (1 if i < flaky_once else 2) for i, key in enumerate(flaky_keys)}

        task_of = {p["product_id"]: p["task_id"] for p in products}
        runs: list[tuple] = []
        prices: list[tuple] = []
        run_id = 0
        base_price = Decimal("249.00")

        for p_index, product in enumerate(products):
            pid = product["product_id"]
            for slot_index in range(slots_per_day * args.days):
                slot_at = start + timedelta(seconds=slot_index * args.interval)
                if (pid, slot_index) in down_keys:
                    run_id += 1
                    runs.append(
                        (run_id, task_of[pid], pid, slot_at, 1, "failed", slot_at + timedelta(seconds=2),
                         1800, "not_found", "product offline (410 Gone)")
                    )
                    continue

                attempts = 1 + flaky.get((pid, slot_index), 0)
                for attempt in range(1, attempts + 1):
                    run_id += 1
                    if attempt < attempts:
                        runs.append(
                            (run_id, task_of[pid], pid, slot_at, attempt, "failed",
                             slot_at + timedelta(seconds=300), 300_000, "timeout",
                             "page.goto: Timeout 30000ms exceeded")
                        )
                        continue

                    runs.append(
                        (run_id, task_of[pid], pid, slot_at, attempt, "success",
                         slot_at + timedelta(seconds=4), 1600 + (p_index % 5) * 120, None, None)
                    )
                    price = (base_price + Decimal(p_index * 17) + Decimal((slot_index % 23) * 3)).quantize(
                        Decimal("0.01")
                    )
                    prices.append((pid, run_id, price, True, slot_at))

        print(
            f"planned={total_planned} success={success_slots} flaky_failed_attempts={failed_attempts} "
            f"down={not_found_slots} expected_runs={expected_runs}"
        )
        print(f"generated runs={len(runs)} prices={len(prices)}")

        await conn.executemany(
            """
            INSERT INTO task_runs (id, task_id, product_id, slot_at, attempt, status, queued_at,
                                   started_at, finished_at, duration_ms, error_type, error_msg, worker_id)
            VALUES ($1, $2, $3, $4, $5, $6, $4, $7, $7, $8, $9, $10, 'worker-demo-01')
            ON CONFLICT (task_id, slot_at, attempt) DO NOTHING
            """,
            runs,
        )
        await conn.executemany(
            """
            INSERT INTO price_records (product_id, run_id, price, currency, in_stock, collected_at, raw)
            VALUES ($1, $2, $3, 'CNY', $4, $5, '{"source":"demo-4d"}')
            ON CONFLICT (product_id, collected_at) DO NOTHING
            """,
            prices,
        )
        await conn.execute("UPDATE tasks SET next_run_at = now() + interval '30 minutes'")
        # 显式插入 id 后必须校准序列，否则后续 INSERT 会撞主键
        await conn.execute("SELECT setval('task_runs_id_seq', COALESCE((SELECT max(id) FROM task_runs), 1))")

        counts = await conn.fetchrow(
            """
            SELECT (SELECT count(*) FROM task_runs) AS runs,
                   (SELECT count(*) FROM price_records) AS prices,
                   (SELECT count(*) FROM task_runs WHERE status = 'success') AS ok,
                   (SELECT count(*) FROM task_runs WHERE error_type = 'not_found') AS down
            """
        )
        print(dict(counts))

    await pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))


