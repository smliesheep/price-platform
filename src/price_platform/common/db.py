"""PostgreSQL 连接：asyncpg 池（调度/Worker/Reaper 热路径）+ 选主锁。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg

from price_platform.common.settings import Settings


def sqlalchemy_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


async def create_pool(settings: Settings) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=20,
        server_settings={"application_name": settings.pod},
    )


async def acquire_advisory_lock(dsn: str, name: str) -> asyncpg.Connection | None:
    """会话级 advisory lock：拿到返回连接（需常驻），拿不到返回 None。

    用独立连接而不是池，避免连接被归还后锁被释放。
    """
    conn = await asyncpg.connect(dsn=dsn, command_timeout=20)
    try:
        got = await conn.fetchval("SELECT pg_try_advisory_lock(hashtext($1))", name)
    except Exception:
        await conn.close()
        raise
    if not got:
        await conn.close()
        return None
    return conn


@asynccontextmanager
async def transaction(pool: asyncpg.Pool) -> AsyncIterator[asyncpg.Connection]:
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn
