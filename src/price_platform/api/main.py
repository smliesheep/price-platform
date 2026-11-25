"""FastAPI 应用：中间件、异常、路由装配、探针。"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from price_platform import __version__
from price_platform.api.deps import engine
from price_platform.api.routers import (
    alerts,
    auth,
    overview,
    products,
    runs,
    sources,
    system,
    tasks,
    workers,
)
from price_platform.api.schemas.common import (
    AppError,
    app_error_handler,
    ok,
    validation_error_handler,
)
from price_platform.common import metrics as M
from price_platform.common.logging import get_logger, setup_logging, trace_id_var
from price_platform.common.queue import new_trace_id, redis_client
from price_platform.common.settings import settings

log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging("api")
    app.state.redis = redis_client(settings)
    try:
        await app.state.redis.ping()
    except Exception as exc:  # noqa: BLE001 - 启动早期 Redis 不可用不应阻塞 API
        log.warning("redis_unavailable", error_msg=str(exc))
    log.info("api_started", version=__version__)
    yield
    await app.state.redis.aclose()
    await engine.dispose()
    log.info("api_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Price Platform API",
        version=__version__,
        description="基于 Kubernetes 的云原生 RPA 价格监控平台",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Trace-Id"],
    )

    @app.middleware("http")
    async def trace_and_metrics(request: Request, call_next):  # type: ignore[no-untyped-def]
        trace_id = request.headers.get("x-trace-id") or new_trace_id()
        trace_id_var.set(trace_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - 兜底 500 也带上 trace_id
            log.exception("unhandled_error", path=request.url.path)
            response = JSONResponse(
                status_code=500,
                content={
                    "code": 9000,
                    "message": "internal error",
                    "detail": None,
                    "trace_id": trace_id,
                },
            )
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        M.HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        M.HTTP_DURATION.labels(path).observe(time.perf_counter() - started)
        response.headers["X-Trace-Id"] = trace_id
        return response

    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

    for router in (
        auth.router,
        overview.router,
        sources.router,
        products.router,
        tasks.router,
        runs.router,
        workers.router,
        system.router,
        alerts.router,
    ):
        app.include_router(router, prefix="/api/v1")

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "version": __version__}

    @app.get("/readyz")
    async def readyz() -> Response:
        try:
            async with engine.connect() as conn:
                await conn.exec_driver_sql("SELECT 1")
            await app.state.redis.ping()
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(status_code=503, content={"ok": False, "error": str(exc)})
        return JSONResponse(content={"ok": True})

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "price_platform.api.main:app",
        host="0.0.0.0",
        port=8000,
        log_config=None,
        access_log=False,
    )


__all__ = ["app", "create_app", "ok"]


if __name__ == "__main__":
    run()

