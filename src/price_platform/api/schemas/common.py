"""统一响应与错误。"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from price_platform.common.logging import trace_id_var


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"code": 0, "message": message, "data": data, "trace_id": trace_id_var.get()}


def paginated(items: list[Any], total: int, page: int, page_size: int) -> dict[str, Any]:
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


class AppError(Exception):
    def __init__(self, code: int, message: str, status_code: int = 400, detail: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


class NotFound(AppError):
    def __init__(self, message: str = "resource not found", detail: Any = None) -> None:
        super().__init__(1004, message, 404, detail)


class Conflict(AppError):
    def __init__(self, message: str = "resource conflict", detail: Any = None) -> None:
        super().__init__(1005, message, 409, detail)


class BadRequest(AppError):
    def __init__(self, message: str = "invalid request", detail: Any = None) -> None:
        super().__init__(1001, message, 400, detail)


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "detail": exc.detail,
            "trace_id": trace_id_var.get(),
        },
    )


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    detail = getattr(exc, "errors", lambda: str(exc))()
    return JSONResponse(
        status_code=422,
        content={"code": 1001, "message": "validation error", "detail": detail, "trace_id": trace_id_var.get()},
    )
