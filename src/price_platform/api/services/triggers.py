"""手动触发：建一条 queued run 并投递到 Stream。"""

from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from price_platform.api.schemas.common import BadRequest, NotFound
from price_platform.common.logging import get_logger, trace_id_var
from price_platform.common.queue import TaskMessage, publish
from price_platform.common.settings import settings
from price_platform.common.timeutil import utcnow
from price_platform.models.entities import Product, Task, TaskRun

log = get_logger("api")


async def trigger_task(session: AsyncSession, redis: Redis, task_id: int) -> dict:
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFound(f"task {task_id} not found")
    if task.status != "active":
        raise BadRequest(f"task {task_id} is {task.status}, cannot run")

    product = await session.get(Product, task.product_id)
    if product is None:
        raise NotFound(f"product {task.product_id} not found")

    slot = utcnow().replace(microsecond=0)
    run = TaskRun(
        task_id=task.id,
        product_id=task.product_id,
        slot_at=slot,
        attempt=1,
        status="queued",
        trace_id=trace_id_var.get(),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    msg = TaskMessage(
        run_id=run.id,
        task_id=task.id,
        product_id=task.product_id,
        source_id=product.source_id,
        slot_at=slot,
        attempt=1,
        trace_id=run.trace_id or "",
        enqueued_at=utcnow(),
    )
    try:
        await publish(redis, settings, msg)
        run.dispatched_at = utcnow()
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - 投递失败留给 reaper 补发
        log.error("manual_publish_failed", run_id=run.id, error_msg=str(exc))

    return {"run_id": run.id, "slot_at": slot.isoformat(), "task_id": task.id}


async def trigger_product(session: AsyncSession, redis: Redis, product_id: int) -> dict:
    task = await session.scalar(select(Task).where(Task.product_id == product_id))
    if task is None:
        raise NotFound(f"task for product {product_id} not found")
    return await trigger_task(session, redis, task.id)
