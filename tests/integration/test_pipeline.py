"""集成测试：真实 Postgres + Redis 上验证调度、抢占、幂等。

前置：
    docker compose -f deploy/compose/docker-compose.dev.yml up -d postgres redis
    alembic upgrade head
运行：
    pytest -m integration -q
"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta

import asyncpg
import pytest
from redis.asyncio import Redis

from price_platform.common.queue import TaskMessage, ensure_group, publish
from price_platform.common.settings import Settings
from price_platform.common.timeutil import utcnow
from price_platform.scheduler.service import tick

pytestmark = pytest.mark.integration

DB_URL = os.getenv("PP_TEST_DATABASE_URL", "postgresql://price:price@127.0.0.1:55432/price")
REDIS_URL = os.getenv("PP_TEST_REDIS_URL", "redis://127.0.0.1:56379/0")


@pytest.fixture()
async def settings() -> Settings:
    return Settings(
        database_url=DB_URL,
        redis_url=REDIS_URL,
        queue_stream=f"test:tasks:{uuid.uuid4().hex[:8]}",
        queue_group="test-workers",
        queue_dlq=f"test:dlq:{uuid.uuid4().hex[:8]}",
        retry_zset=f"test:retry:{uuid.uuid4().hex[:8]}",
        scheduler_batch=50,
        promote_interval_sec=1,
    )


@pytest.fixture()
async def pool(settings: Settings):
    pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=3)
    yield pool
    await pool.close()


@pytest.fixture()
async def redis(settings: Settings):
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    await ensure_group(client, settings)
    yield client
    await client.delete(settings.queue_stream, settings.queue_dlq, settings.retry_zset)
    await client.aclose()


async def _cleanup(conn: asyncpg.Connection, source_id: int) -> None:
    await conn.execute("DELETE FROM products WHERE source_id = $1", source_id)
    await conn.execute("DELETE FROM sources WHERE id = $1", source_id)


async def _create_task(conn: asyncpg.Connection, *, due_seconds_ago: int = 60) -> tuple[int, int]:
    suffix = uuid.uuid4().hex[:8]
    source_id = await conn.fetchval(
        "INSERT INTO sources (name, base_url, adapter) VALUES ($1, $2, 'mock') RETURNING id",
        f"itest-{suffix}",
        "http://mock-shop:8080",
    )
    product_id = await conn.fetchval(
        """
        INSERT INTO products (source_id, external_id, title, url)
        VALUES ($1, $2, $3, $4) RETURNING id
        """,
        source_id,
        f"p-{suffix}",
        f"itest product {suffix}",
        "/p/1001",
    )
    task_id = await conn.fetchval(
        """
        INSERT INTO tasks (product_id, schedule_type, interval_sec, next_run_at)
        VALUES ($1, 'interval', 1800, $2) RETURNING id
        """,
        product_id,
        utcnow() - timedelta(seconds=due_seconds_ago),
    )
    return source_id, task_id


async def test_tick_creates_run_and_publishes(pool: asyncpg.Pool, redis: Redis, settings: Settings) -> None:
    async with pool.acquire() as conn:
        source_id, task_id = await _create_task(conn)

    stats = await tick(pool, redis, settings)
    assert stats.dispatched >= 1

    async with pool.acquire() as conn:
        run = await conn.fetchrow(
            "SELECT id, status, dispatched_at, slot_at FROM task_runs WHERE task_id = $1", task_id
        )
        task = await conn.fetchrow("SELECT next_run_at, last_run_at FROM tasks WHERE id = $1", task_id)
        await _cleanup(conn, source_id)

    assert run is not None
    assert run["status"] == "queued"
    assert run["dispatched_at"] is not None
    assert task["next_run_at"] > utcnow()
    assert task["last_run_at"] == run["slot_at"]

    entries = await redis.xrange(settings.queue_stream)
    assert any(fields["run_id"] == str(run["id"]) for _, fields in entries)


async def test_claim_is_exclusive(pool: asyncpg.Pool, settings: Settings) -> None:
    async with pool.acquire() as conn:
        source_id, task_id = await _create_task(conn)
        run_id = await conn.fetchval(
            """
            INSERT INTO task_runs (task_id, product_id, slot_at, attempt, status)
            SELECT $1, product_id, now(), 1, 'queued' FROM tasks WHERE id = $1
            RETURNING id
            """,
            task_id,
        )

        claim_sql = """
            UPDATE task_runs SET status='running', worker_id=$2, started_at=now()
            WHERE id=$1 AND status='queued'
        """
        first = await conn.execute(claim_sql, run_id, "worker-a")
        second = await conn.execute(claim_sql, run_id, "worker-b")
        row = await conn.fetchrow("SELECT worker_id FROM task_runs WHERE id=$1", run_id)
        await _cleanup(conn, source_id)

    assert first.endswith("1")
    assert second.endswith("0")
    assert row["worker_id"] == "worker-a"


async def test_price_unique_key(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        source_id, task_id = await _create_task(conn)
        product_id = await conn.fetchval("SELECT product_id FROM tasks WHERE id=$1", task_id)
        slot = utcnow().replace(microsecond=0)

        insert = """
            INSERT INTO price_records (product_id, price, collected_at)
            VALUES ($1, $2, $3) ON CONFLICT (product_id, collected_at) DO NOTHING
        """
        await conn.execute(insert, product_id, 100.0, slot)
        await conn.execute(insert, product_id, 101.0, slot)
        count = await conn.fetchval(
            "SELECT count(*) FROM price_records WHERE product_id=$1 AND collected_at=$2", product_id, slot
        )
        await _cleanup(conn, source_id)

    assert count == 1


async def test_message_roundtrip_against_stream(pool: asyncpg.Pool, redis: Redis, settings: Settings) -> None:
    msg = TaskMessage(
        run_id=999999,
        task_id=1,
        product_id=1,
        source_id=1,
        slot_at=utcnow(),
        attempt=1,
        trace_id="itest",
        enqueued_at=utcnow(),
    )
    await publish(redis, settings, msg)
    entries = await redis.xrange(settings.queue_stream)
    assert len(entries) == 1
    assert TaskMessage.from_fields(entries[0][1]) == msg

