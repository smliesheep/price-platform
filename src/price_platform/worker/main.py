"""worker 进程入口：预热浏览器、N 个消费协程、心跳、优雅退出。"""

from __future__ import annotations

import asyncio
import signal

from price_platform import __version__
from price_platform.common.db import create_pool
from price_platform.common.logging import get_logger, setup_logging
from price_platform.common.metrics import start_admin_server
from price_platform.common.queue import ensure_group, redis_client
from price_platform.common.settings import settings
from price_platform.worker.adapters import build_adapters
from price_platform.worker.browser import BrowserManager
from price_platform.worker.consumer import WorkerContext, consume_loop, heartbeat_loop
from price_platform.worker.ratelimit import RateLimiter
from price_platform.worker.selectors import SelectorStore

log = get_logger("worker")
DRAIN_TIMEOUT = 40


async def _drain(ctx: WorkerContext) -> None:
    deadline = asyncio.get_event_loop().time() + DRAIN_TIMEOUT
    while ctx.inflight > 0 and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.5)
    if ctx.inflight > 0:
        log.warning("drain_timeout", inflight=ctx.inflight)


async def main() -> int:
    setup_logging("worker")

    pool = await create_pool(settings)
    redis = redis_client(settings)
    await ensure_group(redis, settings)

    browser = BrowserManager(settings)
    ctx = WorkerContext(
        settings=settings,
        pool=pool,
        redis=redis,
        browser=browser,
        adapters=build_adapters(settings),
        selectors=SelectorStore(settings.selector_dir),
        limiter=RateLimiter(redis),
    )

    try:
        await browser.start()
    except Exception as exc:  # noqa: BLE001 - 浏览器起不来时 Worker 没有存在意义
        log.error("browser_start_failed", error_msg=str(exc))
        await redis.aclose()
        await pool.close()
        return 1

    async def ready() -> None:
        await pool.fetchval("SELECT 1")
        await redis.ping()

    admin = await start_admin_server(settings.metrics_port, ready)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, ctx.stop_event.set)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda *_: ctx.stop_event.set())

    tasks = [
        asyncio.create_task(consume_loop(ctx, slot), name=f"consume-{slot}")
        for slot in range(settings.worker_concurrency)
    ]
    tasks.append(asyncio.create_task(heartbeat_loop(ctx, __version__), name="heartbeat"))

    log.info(
        "worker_started",
        concurrency=settings.worker_concurrency,
        stream=settings.queue_stream,
        group=settings.queue_group,
        pod=settings.pod,
    )

    await ctx.stop_event.wait()
    log.info("worker_stopping", inflight=ctx.inflight)
    ctx.stopping = True
    await _drain(ctx)

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    await browser.close()
    try:
        await pool.execute("DELETE FROM workers WHERE id = $1", settings.pod)
    except Exception:  # noqa: BLE001
        pass
    await admin.cleanup()
    await redis.aclose()
    await pool.close()
    log.info("worker_stopped")
    return 0


def run() -> None:
    raise SystemExit(asyncio.run(main()))


if __name__ == "__main__":
    run()
