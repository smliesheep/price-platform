"""reaper 进程入口：15s 一轮，四个幂等动作。"""

from __future__ import annotations

import asyncio
import signal

from price_platform.common.db import create_pool
from price_platform.common.logging import get_logger, setup_logging
from price_platform.common.metrics import start_admin_server
from price_platform.common.queue import ensure_group, redis_client
from price_platform.common.settings import settings
from price_platform.reaper.service import run_once

log = get_logger("reaper")


async def main() -> int:
    setup_logging("reaper")
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

    log.info("reaper_started", interval=settings.reaper_interval_sec)
    while not stop.is_set():
        try:
            await run_once(pool, redis, settings)
        except Exception as exc:  # noqa: BLE001
            log.exception("reaper_tick_failed", error_msg=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.reaper_interval_sec)
        except asyncio.TimeoutError:
            pass

    await admin.cleanup()
    await redis.aclose()
    await pool.close()
    log.info("reaper_stopped")
    return 0


def run() -> None:
    raise SystemExit(asyncio.run(main()))


if __name__ == "__main__":
    run()
