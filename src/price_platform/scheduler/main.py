"""scheduler 进程入口：选主、双循环、优雅退出。"""

from __future__ import annotations

import asyncio
import signal

from price_platform.common.db import acquire_advisory_lock, create_pool
from price_platform.common.logging import get_logger, setup_logging
from price_platform.common.metrics import start_admin_server
from price_platform.common.queue import ensure_group, redis_client
from price_platform.common.settings import settings
from price_platform.scheduler.service import promote_due_retries, tick

log = get_logger("scheduler")
LOCK_NAME = "price:scheduler"


async def _wait(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def due_loop(pool, redis, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await tick(pool, redis, settings)
        except Exception as exc:  # noqa: BLE001 - 循环不能死
            log.exception("scheduler_tick_failed", error_msg=str(exc))
        await _wait(stop, settings.scheduler_tick_sec)


async def promote_loop(pool, redis, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await promote_due_retries(pool, redis, settings)
        except Exception as exc:  # noqa: BLE001
            log.exception("promote_failed", error_msg=str(exc))
        await _wait(stop, settings.promote_interval_sec)


async def main() -> int:
    setup_logging("scheduler")

    lock_conn = await acquire_advisory_lock(settings.database_url, LOCK_NAME)
    if lock_conn is None:
        log.error("scheduler_lock_busy", msg="another scheduler holds the lock, exiting")
        return 0

    pool = await create_pool(settings)
    redis = redis_client(settings)
    await ensure_group(redis, settings)

    async def ready() -> None:
        await pool.fetchval("SELECT 1")
        await redis.ping()

    admin = await start_admin_server(settings.metrics_port, ready)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda *_: stop.set())

    log.info("scheduler_started", tick=settings.scheduler_tick_sec, batch=settings.scheduler_batch)
    tasks = [
        asyncio.create_task(due_loop(pool, redis, stop), name="due_loop"),
        asyncio.create_task(promote_loop(pool, redis, stop), name="promote_loop"),
    ]
    await stop.wait()
    log.info("scheduler_stopping")

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    await admin.cleanup()
    await redis.aclose()
    await pool.close()
    await lock_conn.close()
    log.info("scheduler_stopped")
    return 0


def run() -> None:
    raise SystemExit(asyncio.run(main()))


if __name__ == "__main__":
    run()
