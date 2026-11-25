"""站点源 CRUD。"""

from __future__ import annotations

from decimal import Decimal  # noqa: F401  (保留给未来扩展)

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from price_platform.api.deps import CurrentUser, SessionDep
from price_platform.api.schemas.common import NotFound, ok
from price_platform.models.entities import Source

router = APIRouter(tags=["sources"])


class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    base_url: str
    adapter: str = "mock"
    rate_limit_per_min: int = Field(default=60, ge=1, le=6000)
    proxy_group: str | None = None
    enabled: bool = True


class SourcePatch(BaseModel):
    name: str | None = None
    base_url: str | None = None
    adapter: str | None = None
    rate_limit_per_min: int | None = Field(default=None, ge=1, le=6000)
    proxy_group: str | None = None
    enabled: bool | None = None


def _serialize(source: Source) -> dict:
    return {
        "id": source.id,
        "name": source.name,
        "base_url": source.base_url,
        "adapter": source.adapter,
        "rate_limit_per_min": source.rate_limit_per_min,
        "proxy_group": source.proxy_group,
        "enabled": source.enabled,
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
    }


@router.get("/sources")
async def list_sources(session: SessionDep, user: CurrentUser) -> dict:
    del user
    sources = (await session.scalars(select(Source).order_by(Source.id))).all()
    return ok([_serialize(s) for s in sources])


@router.post("/sources", status_code=201)
async def create_source(payload: SourceIn, session: SessionDep, user: CurrentUser) -> dict:
    del user
    existing = await session.scalar(select(Source).where(Source.name == payload.name))
    if existing:
        from price_platform.api.schemas.common import Conflict

        raise Conflict(f"source name already exists: {payload.name}")
    source = Source(**payload.model_dump())
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return ok(_serialize(source))


@router.patch("/sources/{source_id}")
async def update_source(source_id: int, payload: SourcePatch, session: SessionDep, user: CurrentUser) -> dict:
    del user
    source = await session.get(Source, source_id)
    if source is None:
        raise NotFound(f"source {source_id} not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, key, value)
    await session.commit()
    await session.refresh(source)
    return ok(_serialize(source))
