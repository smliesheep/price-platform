"""API 依赖：DB 会话、鉴权、分页、Redis。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, AsyncIterator

import jwt
from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from price_platform.common.db import sqlalchemy_url
from price_platform.common.security import decode_token
from price_platform.common.settings import settings

engine = create_async_engine(
    sqlalchemy_url(settings.database_url),
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination(
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


PaginationDep = Annotated[Pagination, Depends(pagination)]


async def get_current_user(authorization: str | None = Header(default=None)) -> str:
    if settings.disable_auth:
        return "anonymous"
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="token expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    return str(payload.get("sub") or "admin")


CurrentUser = Annotated[str, Depends(get_current_user)]
