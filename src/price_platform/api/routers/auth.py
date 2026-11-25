"""登录与当前用户。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from price_platform.api.deps import CurrentUser
from price_platform.api.schemas.common import AppError, ok
from price_platform.common.security import create_token, verify_password
from price_platform.common.settings import settings

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(payload: LoginIn) -> dict:
    if payload.username != settings.admin_username or not verify_password(
        payload.password, settings.admin_password_hash
    ):
        raise AppError(1002, "invalid username or password", 401)
    token = create_token(payload.username)
    return ok(
        {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.jwt_expire_min * 60,
            "username": payload.username,
        }
    )


@router.get("/auth/me")
async def me(user: CurrentUser) -> dict:
    return ok({"username": user, "auth_disabled": settings.disable_auth})
