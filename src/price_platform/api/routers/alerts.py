"""告警：查询 + Alertmanager webhook 接收。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel
from sqlalchemy import select

from price_platform.api.deps import CurrentUser, SessionDep
from price_platform.api.schemas.common import ok
from price_platform.common.logging import get_logger
from price_platform.common.timeutil import utcnow
from price_platform.models.entities import Alert

router = APIRouter(tags=["alerts"])
log = get_logger("api")


class AlertItem(BaseModel):
    status: str | None = None
    labels: dict | None = None
    annotations: dict | None = None
    startsAt: str | None = None
    endsAt: str | None = None


class AlertmanagerPayload(BaseModel):
    status: str | None = None
    alerts: list[AlertItem] = []


async def _store(payload: AlertmanagerPayload, session: SessionDep) -> None:
    del session  # 由调用方注入新 session
    return None


@router.get("/alerts")
async def list_alerts(session: SessionDep, user: CurrentUser, limit: int = 50) -> dict:
    del user
    rows = (
        await session.scalars(select(Alert).order_by(Alert.triggered_at.desc()).limit(min(limit, 200)))
    ).all()
    items = [
        {
            "id": a.id,
            "product_id": a.product_id,
            "rule": a.rule,
            "level": a.level,
            "payload": a.payload,
            "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        }
        for a in rows
    ]
    return ok({"items": items, "total": len(items)})


@router.post("/alerts/webhook", include_in_schema=False)
async def alertmanager_webhook(
    payload: AlertmanagerPayload,
    request: Request,
    background: BackgroundTasks,
) -> dict:
    """Alertmanager 推送入口：把 Prometheus 告警落库，页面可查。"""
    from price_platform.api.deps import SessionLocal

    async def _persist() -> None:
        async with SessionLocal() as session:
            for item in payload.alerts:
                labels = item.labels or {}
                session.add(
                    Alert(
                        product_id=None,
                        rule=labels.get("alertname", "prometheus"),
                        level="crit" if item.status == "firing" else "info",
                        payload={
                            "status": item.status,
                            "labels": labels,
                            "annotations": item.annotations or {},
                            "startsAt": item.startsAt,
                        },
                        triggered_at=utcnow(),
                        resolved_at=None if item.status == "firing" else utcnow(),
                    )
                )
            await session.commit()
        log.info("alerts_stored", count=len(payload.alerts))

    background.add_task(_persist)
    return {"ok": True, "received": len(payload.alerts)}
