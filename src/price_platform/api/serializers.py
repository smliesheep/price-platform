"""ORM/行记录 → API JSON 的序列化。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _money(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def product_out(product: Any, source_name: str | None = None, task: Any = None) -> dict:
    payload = {
        "id": product.id,
        "source_id": product.source_id,
        "source_name": source_name,
        "external_id": product.external_id,
        "title": product.title,
        "url": product.url,
        "category": product.category,
        "target_price": _money(product.target_price),
        "selector_version": product.selector_version,
        "enabled": product.enabled,
        "current_price": _money(product.current_price),
        "last_collected_at": _dt(product.last_collected_at),
        "last_status": product.last_status,
        "created_at": _dt(product.created_at),
        "updated_at": _dt(product.updated_at),
    }
    if task is not None:
        payload["task"] = task_out(task)
    return payload


def task_out(task: Any) -> dict:
    return {
        "id": task.id,
        "product_id": task.product_id,
        "schedule_type": task.schedule_type,
        "interval_sec": task.interval_sec,
        "cron_expr": task.cron_expr,
        "priority": task.priority,
        "status": task.status,
        "next_run_at": _dt(task.next_run_at),
        "last_run_at": _dt(task.last_run_at),
        "max_retry": task.max_retry,
        "timeout_sec": task.timeout_sec,
    }


def run_out(run: Any, product_title: str | None = None) -> dict:
    return {
        "id": run.id,
        "task_id": run.task_id,
        "product_id": run.product_id,
        "product_title": product_title,
        "slot_at": _dt(run.slot_at),
        "attempt": run.attempt,
        "status": run.status,
        "worker_id": run.worker_id,
        "trace_id": run.trace_id,
        "queued_at": _dt(run.queued_at),
        "started_at": _dt(run.started_at),
        "finished_at": _dt(run.finished_at),
        "duration_ms": run.duration_ms,
        "http_status": run.http_status,
        "error_type": run.error_type,
        "error_msg": run.error_msg,
    }
