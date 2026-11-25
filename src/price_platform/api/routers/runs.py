"""执行记录检索。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from price_platform.api.deps import CurrentUser, PaginationDep, SessionDep
from price_platform.api.schemas.common import NotFound, ok, paginated
from price_platform.api.serializers import run_out
from price_platform.models.entities import Product, TaskRun

router = APIRouter(tags=["runs"])


@router.get("/runs")
async def list_runs(
    session: SessionDep,
    user: CurrentUser,
    page: PaginationDep,
    status: str | None = None,
    error_type: str | None = None,
    worker_id: str | None = None,
    product_id: int | None = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
) -> dict:
    del user
    filters = []
    if status:
        filters.append(TaskRun.status == status)
    if error_type:
        filters.append(TaskRun.error_type == error_type)
    if worker_id:
        filters.append(TaskRun.worker_id == worker_id)
    if product_id is not None:
        filters.append(TaskRun.product_id == product_id)
    if from_:
        filters.append(TaskRun.queued_at >= from_)
    if to:
        filters.append(TaskRun.queued_at <= to)

    stmt = (
        select(TaskRun, Product.title)
        .join(Product, Product.id == TaskRun.product_id)
        .order_by(TaskRun.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    )
    count_stmt = select(func.count()).select_from(TaskRun)
    for condition in filters:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    rows = (await session.execute(stmt)).all()
    total = int(await session.scalar(count_stmt) or 0)
    return paginated([run_out(run, title) for run, title in rows], total, page.page, page.page_size)


@router.get("/runs/{run_id}")
async def get_run(run_id: int, session: SessionDep, user: CurrentUser) -> dict:
    del user
    row = (
        await session.execute(
            select(TaskRun, Product.title, Product.url)
            .join(Product, Product.id == TaskRun.product_id)
            .where(TaskRun.id == run_id)
        )
    ).first()
    if row is None:
        raise NotFound(f"run {run_id} not found")
    run, title, url = row
    return ok({**run_out(run, title), "product_url": url})
