"""Worker 心跳与在线状态。"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from price_platform.api.deps import CurrentUser, SessionDep
from price_platform.api.schemas.common import ok
from price_platform.common.settings import settings
from price_platform.common.timeutil import utcnow
from price_platform.models.entities import Worker

router = APIRouter(tags=["workers"])


@router.get("/workers")
async def list_workers(session: SessionDep, user: CurrentUser) -> dict:
    del user
    workers = (await session.scalars(select(Worker).order_by(Worker.id))).all()
    now = utcnow()
    items = []
    for worker in workers:
        age = (now - worker.last_heartbeat).total_seconds() if worker.last_heartbeat else None
        items.append(
            {
                "id": worker.id,
                "node": worker.node,
                "version": worker.version,
                "inflight": worker.inflight,
                "last_heartbeat": worker.last_heartbeat.isoformat() if worker.last_heartbeat else None,
                "heartbeat_age_sec": int(age) if age is not None else None,
                "online": age is not None and age < settings.worker_heartbeat_timeout_sec,
            }
        )
    return ok({"items": items, "online": sum(1 for i in items if i["online"])})
