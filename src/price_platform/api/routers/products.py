"""商品：列表、创建（URL 预览）、详情、修改、启停、手动采集、价格曲线。"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from price_platform.api.deps import CurrentUser, PaginationDep, SessionDep
from price_platform.api.schemas.common import BadRequest, Conflict, NotFound, ok, paginated
from price_platform.api.serializers import product_out, run_out
from price_platform.api.services.preview import guess_external_id, preview
from price_platform.api.services.triggers import trigger_product
from price_platform.common.timeutil import utcnow
from price_platform.models.entities import PriceRecord, Product, Source, Task, TaskRun
from price_platform.worker.selectors import SelectorStore

router = APIRouter(tags=["products"])


class ProductIn(BaseModel):
    source_id: int
    url: str = Field(min_length=1)
    title: str | None = None
    category: str | None = None
    target_price: Decimal | None = Field(default=None, gt=0)
    interval_sec: int = Field(default=1800, ge=60, le=7 * 24 * 3600)
    selector_version: str = "v1"
    external_id: str | None = None


class ProductPatch(BaseModel):
    title: str | None = None
    category: str | None = None
    target_price: Decimal | None = Field(default=None, gt=0)
    selector_version: str | None = None
    url: str | None = None


class ToggleIn(BaseModel):
    enabled: bool


async def _get_product(session: AsyncSession, product_id: int) -> tuple[Product, str, Task | None]:
    row = (
        await session.execute(
            select(Product, Source.name, Task)
            .join(Source, Source.id == Product.source_id)
            .outerjoin(Task, Task.product_id == Product.id)
            .where(Product.id == product_id)
        )
    ).first()
    if row is None:
        raise NotFound(f"product {product_id} not found")
    return row[0], row[1], row[2]


@router.get("/products")
async def list_products(
    session: SessionDep,
    user: CurrentUser,
    page: PaginationDep,
    q: str | None = None,
    source_id: int | None = None,
    enabled: bool | None = None,
) -> dict:
    del user
    filters = []
    if q:
        filters.append(Product.title.ilike(f"%{q}%"))
    if source_id is not None:
        filters.append(Product.source_id == source_id)
    if enabled is not None:
        filters.append(Product.enabled == enabled)

    stmt = (
        select(Product, Source.name, Task)
        .join(Source, Source.id == Product.source_id)
        .outerjoin(Task, Task.product_id == Product.id)
        .order_by(Product.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    )
    count_stmt = select(func.count()).select_from(Product)
    for condition in filters:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    rows = (await session.execute(stmt)).all()
    total = int(await session.scalar(count_stmt) or 0)
    items = [product_out(p, name, task) for p, name, task in rows]
    return paginated(items, total, page.page, page.page_size)


@router.post("/products", status_code=201)
async def create_product(payload: ProductIn, session: SessionDep, user: CurrentUser) -> dict:
    del user
    source = await session.get(Source, payload.source_id)
    if source is None:
        raise NotFound(f"source {payload.source_id} not found")

    url = payload.url
    if not url.startswith("http"):
        url = source.base_url.rstrip("/") + "/" + url.lstrip("/")

    external_id = payload.external_id or guess_external_id(url)
    duplicate = await session.scalar(
        select(Product).where(Product.source_id == source.id, Product.external_id == external_id)
    )
    if duplicate is not None:
        raise Conflict(f"product already exists: id={duplicate.id}")

    title = payload.title
    current_price: Decimal | None = None
    if not title:
        selectors = SelectorStore("./configs/selectors").get(source.adapter, payload.selector_version)
        try:
            info = await preview(url, selectors)
            title = str(info["title"]) if info.get("title") else None
            current_price = info.get("price")  # type: ignore[assignment]
        except Exception:  # noqa: BLE001 - 预览失败不阻塞创建
            title = None

    product = Product(
        source_id=source.id,
        external_id=external_id,
        title=title or f"商品 {external_id}",
        url=url,
        category=payload.category,
        target_price=payload.target_price,
        selector_version=payload.selector_version,
        current_price=current_price,
        last_collected_at=None,
        last_status="success" if current_price is not None else None,
    )
    session.add(product)
    await session.flush()

    task = Task(
        product_id=product.id,
        schedule_type="interval",
        interval_sec=payload.interval_sec,
        priority=5,
        status="active",
        next_run_at=utcnow() + timedelta(seconds=payload.interval_sec),
    )
    session.add(task)
    await session.commit()
    await session.refresh(product)
    await session.refresh(task)
    return ok(product_out(product, source.name, task))


@router.get("/products/{product_id}")
async def get_product(product_id: int, session: SessionDep, user: CurrentUser) -> dict:
    del user
    product, source_name, task = await _get_product(session, product_id)
    return ok(product_out(product, source_name, task))


@router.patch("/products/{product_id}")
async def update_product(
    product_id: int, payload: ProductPatch, session: SessionDep, user: CurrentUser
) -> dict:
    del user
    product, source_name, task = await _get_product(session, product_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    await session.commit()
    await session.refresh(product)
    return ok(product_out(product, source_name, task))


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: int, session: SessionDep, user: CurrentUser) -> None:
    del user
    product = await session.get(Product, product_id)
    if product is None:
        raise NotFound(f"product {product_id} not found")
    await session.delete(product)
    await session.commit()


@router.post("/products/{product_id}/enable")
async def enable_product(product_id: int, session: SessionDep, user: CurrentUser) -> dict:
    del user
    product, source_name, task = await _get_product(session, product_id)
    product.enabled = True
    if task is not None:
        task.status = "active"
        if task.next_run_at is None or task.next_run_at <= utcnow():
            task.next_run_at = utcnow() + timedelta(seconds=task.interval_sec)
    await session.commit()
    await session.refresh(product)
    return ok(product_out(product, source_name, task))


@router.post("/products/{product_id}/disable")
async def disable_product(product_id: int, session: SessionDep, user: CurrentUser) -> dict:
    del user
    product, source_name, task = await _get_product(session, product_id)
    product.enabled = False
    if task is not None:
        task.status = "paused"
    await session.commit()
    await session.refresh(product)
    return ok(product_out(product, source_name, task))


@router.post("/products/{product_id}/run", status_code=202)
async def run_product(product_id: int, request: Request, session: SessionDep, user: CurrentUser) -> dict:
    del user
    _, _, _ = await _get_product(session, product_id)
    result = await trigger_product(session, request.app.state.redis, product_id)
    return ok(result, message="accepted")


@router.get("/products/{product_id}/prices")
async def product_prices(
    product_id: int,
    session: SessionDep,
    user: CurrentUser,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    granularity: Literal["raw", "1h", "1d"] = "raw",
) -> dict:
    del user
    product, _, _ = await _get_product(session, product_id)

    end = to or utcnow()
    start = from_ or (end - timedelta(days=7))
    if start >= end:
        raise BadRequest("from must be earlier than to")

    if granularity == "raw":
        stmt = (
            select(PriceRecord)
            .where(
                PriceRecord.product_id == product_id,
                PriceRecord.collected_at >= start,
                PriceRecord.collected_at <= end,
            )
            .order_by(PriceRecord.collected_at.asc())
            .limit(2000)
        )
        rows = (await session.scalars(stmt)).all()
        points = [
            {"t": r.collected_at.isoformat(), "price": float(r.price), "in_stock": r.in_stock}
            for r in rows
        ]
        downsampled = len(rows) >= 2000
    else:
        unit = "hour" if granularity == "1h" else "day"
        sql = text(
            """
            SELECT DISTINCT ON (bucket) bucket, price, in_stock
            FROM (
                SELECT date_trunc(:unit, collected_at) AS bucket, collected_at, price, in_stock
                FROM price_records
                WHERE product_id = :pid AND collected_at BETWEEN :start AND :end
            ) s
            ORDER BY bucket, collected_at DESC
            """
        )
        rows = (
            await session.execute(sql, {"unit": unit, "pid": product_id, "start": start, "end": end})
        ).all()
        points = [
            {"t": row.bucket.isoformat(), "price": float(row.price), "in_stock": row.in_stock}
            for row in rows
        ]
        downsampled = False

    return ok(
        {
            "granularity": granularity,
            "currency": "CNY",
            "target_price": float(product.target_price) if product.target_price else None,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "downsampled": downsampled,
            "points": points,
        }
    )


@router.get("/products/{product_id}/runs")
async def product_runs(
    product_id: int,
    session: SessionDep,
    user: CurrentUser,
    page: PaginationDep,
) -> dict:
    del user
    _, _, _ = await _get_product(session, product_id)
    stmt = (
        select(TaskRun)
        .where(TaskRun.product_id == product_id)
        .order_by(TaskRun.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    )
    total = int(
        await session.scalar(select(func.count()).select_from(TaskRun).where(TaskRun.product_id == product_id))
        or 0
    )
    runs = (await session.scalars(stmt)).all()
    return paginated([run_out(r) for r in runs], total, page.page, page.page_size)
