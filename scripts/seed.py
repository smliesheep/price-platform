"""初始化演示数据：1 个站点源 + N 个商品 + 对应采集计划。

用法：
    python scripts/seed.py --interval 1800          # 20 个商品，30 分钟一次
    python scripts/seed.py --interval 60 --limit 5  # 5 个商品，1 分钟一次（演示）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import asyncpg
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from price_platform.common.settings import settings  # noqa: E402
from price_platform.common.timeutil import utcnow  # noqa: E402


async def fetch_catalog(base_url: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{base_url.rstrip('/')}/api/products")
        response.raise_for_status()
        return response.json()["items"]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=1800, help="采集间隔（秒）")
    parser.add_argument("--limit", type=int, default=20, help="商品数量上限")
    parser.add_argument("--adapter", default="mock", choices=["mock", "generic", "http"], help="抓取适配器")
    parser.add_argument("--max-retry", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--mock-url", default=os.getenv("PP_MOCK_SHOP_URL", "http://localhost:8088"))
    parser.add_argument("--source-base-url", default=None, help="写入 sources.base_url 的地址（集群内为 http://mock-shop:8080）")
    args = parser.parse_args()

    catalog = (await fetch_catalog(args.mock_url))[: args.limit]
    print(f"fetched {len(catalog)} products from {args.mock_url}")

    pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=3)
    async with pool.acquire() as conn, conn.transaction():
        source_id = await conn.fetchval(
            """
            INSERT INTO sources (name, base_url, adapter, rate_limit_per_min)
            VALUES ($1, $2, $3, 600)
            ON CONFLICT (name) DO UPDATE
            SET base_url = EXCLUDED.base_url, adapter = EXCLUDED.adapter, updated_at = now()
            RETURNING id
            """,
            "mock-shop",
            args.source_base_url or args.mock_url,
            args.adapter,
        )

        created = 0
        for item in catalog:
            product_id = await conn.fetchval(
                """
                INSERT INTO products (source_id, external_id, title, url, category, target_price, current_price,
                                      last_status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'success')
                ON CONFLICT (source_id, external_id) DO UPDATE
                SET title = EXCLUDED.title, url = EXCLUDED.url, category = EXCLUDED.category,
                    target_price = EXCLUDED.target_price, updated_at = now()
                RETURNING id
                """,
                source_id,
                str(item["id"]),
                item["title"],
                f"/p/{item['id']}",
                item.get("category"),
                round(float(item["price"]) * 0.9, 2),
                item["price"],
            )
            await conn.execute(
                """
                INSERT INTO tasks (product_id, schedule_type, interval_sec, status, next_run_at,
                                   max_retry, timeout_sec)
                VALUES ($1, 'interval', $2, 'active', $3, $4, $5)
                ON CONFLICT (product_id) DO UPDATE
                SET interval_sec = EXCLUDED.interval_sec, max_retry = EXCLUDED.max_retry,
                    timeout_sec = EXCLUDED.timeout_sec, updated_at = now()
                """,
                product_id,
                args.interval,
                utcnow() + timedelta(seconds=5),
                args.max_retry,
                args.timeout,
            )
            created += 1

    print(json.dumps({"source_id": source_id, "products": created, "interval_sec": args.interval}, ensure_ascii=False))
    await pool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))


