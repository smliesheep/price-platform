"""采集计划：查询、修改、暂停/恢复、手动触发。"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from price_platform.api.deps import CurrentUser, PaginationDep, SessionDep
from price_platform.api.schemas.common import BadRequest, NotFound, ok, paginated
from price_platform.api.serializers import task_out
from price_platform.api.services.triggers import trigger_task
from price_platform.common.timeutil import advance_next_run, utcnow
from price_platform.models.entities import Product, Task

router = APIRouter(tags=["tasks"])


class TaskPatch(BaseModel):
    schedule_type: str | None = Field(default=None, pattern="^(interval|cron)$")
    interval_sec: int | None = Field(default=None, ge=60, le=7 * 24 * 3600)
    cron_expr: str | None = None
    priority: int | None = Field(default=None, ge=1, le=9)
    max_retry: int | None = Field(default=None, ge=0, le=10)
    timeout_sec: int | None = Field(default=None, ge=30, le=1800)


@router.get("/tasks")
async def list_tasks(
    session: SessionDep,
    user: CurrentUser,
    page: PaginationDep,
    status: Annotated[str | None, Query(pattern="^(active|paused|archived)$")] = None,
) -> dict:
    del user
    stmt = (
        select(Task, Product.title, Product.enabled)
        .join(Product, Product.id == Task.product_id)
        .order_by(Task.next_run_at.asc())
        .limit(page.page_size)
        .offset(page.offset)
    )
    count_stmt = select(func.count()).select_from(Task)
    if status:
        stmt = stmt.where(Task.status == status)
        count_stmt = count_stmt.where(Task.status == status)

    rows = (await session.execute(stmt)).all()
    total = int(await session.scalar(count_stmt) or 0)
    items = [{**task_out(t), "product_title": title, "product_enabled": enabled} for t, title, enabled in rows]
    return paginated(items, total, page.page, page.page_size)


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, session: SessionDep, user: CurrentUser) -> dict:
    del user
    row = (
        await session.execute(
            select(Task, Product.title).join(Product, Product.id == Task.product_id).where(Task.id == task_id)
        )
    ).first()
    if row is None:
        raise NotFound(f"task {task_id} not found")
    task, title = row
    return ok({**task_out(task), "product_title": title})


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, payload: TaskPatch, session: SessionDep, user: CurrentUser) -> dict:
    del user
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFound(f"task {task_id} not found")

    data = payload.model_dump(exclude_unset=True)
    schedule_changed = any(key in data for key in ("schedule_type", "interval_sec", "cron_expr"))
    for key, value in data.items():
        setattr(task, key, value)

    if task.schedule_type == "cron" and not task.cron_expr:
        raise BadRequest("cron_expr is required when schedule_type=cron")

    if schedule_changed and task.status == "active":
        now = utcnow()
        nxt, _ = advance_next_run(
            schedule_type=task.schedule_type,
            interval_sec=task.interval_sec,
            cron_expr=task.cron_expr,
            slot=now,
            now=now,
        )
        task.next_run_at = nxt

    await session.commit()
    await session.refresh(task)
    return ok(task_out(task))


@router.post("/tasks/{task_id}/run", status_code=202)
async def run_task(task_id: int, request: Request, session: SessionDep, user: CurrentUser) -> dict:
    del user
    result = await trigger_task(session, request.app.state.redis, task_id)
    return ok(result, message="accepted")


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: int, session: SessionDep, user: CurrentUser) -> dict:
    del user
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFound(f"task {task_id} not found")
    task.status = "paused"
    await session.commit()
    await session.refresh(task)
    return ok(task_out(task))


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: int, session: SessionDep, user: CurrentUser) -> dict:
    del user
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFound(f"task {task_id} not found")
    task.status = "active"
    task.next_run_at = utcnow() + timedelta(seconds=task.interval_sec)
    await session.commit()
    await session.refresh(task)
    return ok(task_out(task))
