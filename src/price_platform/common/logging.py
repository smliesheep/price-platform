"""结构化日志：一行一个 JSON，字段契约见设计文档 §4.5。"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from price_platform.common.settings import settings

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

_EXTRA_FIELDS = (
    "task_id",
    "run_id",
    "product_id",
    "attempt",
    "duration_ms",
    "error_type",
    "error_msg",
    "http_status",
    "worker_id",
    "event",
    "msg",
)

_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
    | {"message", "asctime", "svc", "pod", "node", "trace_id"}
)


class JsonFormatter(logging.Formatter):
    def __init__(self, svc: str) -> None:
        super().__init__()
        self.svc = svc

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .astimezone()
            .isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "svc": self.svc,
            "pod": settings.pod,
            "trace_id": trace_id_var.get(),
            "event": getattr(record, "event", None) or record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(svc: str, level: str | None = None) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(svc))
    root.addHandler(handler)
    root.setLevel((level or settings.log_level).upper())
    for noisy in ("uvicorn.access", "asyncio", "aiohttp.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel("WARNING")


class _KwargsAdapter(logging.LoggerAdapter):
    """把 log.info("event", key=value) 的 kwargs 塞进 extra，统一成结构化字段。"""

    _PASSTHROUGH = {"exc_info", "stack_info", "stacklevel", "extra"}

    def process(self, msg, kwargs):  # type: ignore[no-untyped-def]
        extra = dict(kwargs.pop("extra", {}) or {})
        for key in list(kwargs.keys()):
            if key not in self._PASSTHROUGH:
                value = kwargs.pop(key)
                # msg 是 Logger 的保留参数名，结构化字段统一改名 note
                extra["note" if key == "msg" else key] = value
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(svc: str) -> logging.LoggerAdapter:
    return _KwargsAdapter(logging.getLogger(svc), {})


