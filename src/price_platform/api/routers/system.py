"""系统状态：队列水位、版本。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from price_platform import __version__
from price_platform.api.deps import CurrentUser
from price_platform.api.schemas.common import ok
from price_platform.common.queue import queue_stats
from price_platform.common.settings import settings

router = APIRouter(tags=["system"])


@router.get("/system/queue")
async def get_queue(request: Request, user: CurrentUser) -> dict:
    del user
    stats = await queue_stats(request.app.state.redis, settings)
    return ok({"stream": settings.queue_stream, "group": settings.queue_group, **stats.as_dict()})


@router.get("/system/version")
async def get_version(user: CurrentUser) -> dict:
    del user
    return ok(
        {
            "version": __version__,
            "stream": settings.queue_stream,
            "group": settings.queue_group,
            "scheduler_tick_sec": settings.scheduler_tick_sec,
            "retry_delay_sec": settings.retry_delay_sec,
            "worker_concurrency": settings.worker_concurrency,
        }
    )
