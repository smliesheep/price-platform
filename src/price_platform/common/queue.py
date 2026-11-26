"""Redis Stream 队列：消息契约、投递、延时重试、队列水位。"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from price_platform.common.settings import Settings
from price_platform.common.timeutil import ensure_utc, parse_rfc3339, to_rfc3339

MESSAGE_VERSION = 1


class MessageFormatError(ValueError):
    """消息字段缺失 / 版本不支持：消费端应 ack 并转 DLQ，避免毒丸重投。"""


@dataclass(frozen=True, slots=True)
class TaskMessage:
    run_id: int
    task_id: int
    product_id: int
    source_id: int
    slot_at: datetime
    attempt: int
    trace_id: str
    enqueued_at: datetime
    v: int = MESSAGE_VERSION

    def to_fields(self) -> dict[str, str]:
        return {
            "v": str(self.v),
            "run_id": str(self.run_id),
            "task_id": str(self.task_id),
            "product_id": str(self.product_id),
            "source_id": str(self.source_id),
            "slot_at": to_rfc3339(self.slot_at),
            "attempt": str(self.attempt),
            "trace_id": self.trace_id,
            "enqueued_at": to_rfc3339(self.enqueued_at),
        }

    @classmethod
    def from_fields(cls, fields: Mapping[str, Any]) -> TaskMessage:
        try:
            version = int(fields.get("v", 1))
            if version != MESSAGE_VERSION:
                raise MessageFormatError(f"unsupported message version: {version}")
            return cls(
                run_id=int(fields["run_id"]),
                task_id=int(fields["task_id"]),
                product_id=int(fields["product_id"]),
                source_id=int(fields["source_id"]),
                slot_at=parse_rfc3339(str(fields["slot_at"])),
                attempt=int(fields["attempt"]),
                trace_id=str(fields.get("trace_id") or ""),
                enqueued_at=parse_rfc3339(str(fields["enqueued_at"])),
                v=version,
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, MessageFormatError):
                raise
            raise MessageFormatError(str(exc)) from exc

    def to_json(self) -> str:
        return json.dumps(self.to_fields(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> TaskMessage:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MessageFormatError(f"bad json: {exc}") from exc
        if not isinstance(payload, dict):
            raise MessageFormatError("message must be a json object")
        return cls.from_fields(payload)

    def next_attempt(self, run_id: int) -> TaskMessage:
        return replace(self, run_id=run_id, attempt=self.attempt + 1)


def redis_client(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


async def ensure_group(redis: Redis, settings: Settings) -> None:
    try:
        await redis.xgroup_create(
            name=settings.queue_stream, groupname=settings.queue_group, id="0", mkstream=True
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def publish(redis: Redis, settings: Settings, msg: TaskMessage) -> str:
    return await redis.xadd(
        settings.queue_stream,
        msg.to_fields(),  # type: ignore[arg-type]
        maxlen=100_000,
        approximate=True,
    )


async def schedule_retry(redis: Redis, settings: Settings, msg: TaskMessage, delay_sec: int) -> None:
    """把"下一次尝试"放进 ZSET，score 是到期毫秒时间戳。"""
    ready_at_ms = int(time.time() * 1000) + delay_sec * 1000
    await redis.zadd(settings.retry_zset, {msg.to_json(): ready_at_ms})


async def due_retries(redis: Redis, settings: Settings, limit: int = 50) -> list[str]:
    now_ms = int(time.time() * 1000)
    return await redis.zrangebyscore(settings.retry_zset, "-inf", now_ms, start=0, num=limit)


async def drop_retry(redis: Redis, settings: Settings, member: str) -> None:
    await redis.zrem(settings.retry_zset, member)


@dataclass(frozen=True, slots=True)
class QueueStats:
    length: int
    pending: int
    lag: int
    dlq: int
    retry_zset: int
    consumers: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "length": self.length,
            "pending": self.pending,
            "lag": self.lag,
            "dlq": self.dlq,
            "retry_zset": self.retry_zset,
            "consumers": self.consumers,
        }


async def queue_stats(redis: Redis, settings: Settings) -> QueueStats:
    length = int(await redis.xlen(settings.queue_stream))
    dlq = int(await redis.xlen(settings.queue_dlq))
    retry_len = int(await redis.zcard(settings.retry_zset))
    pending = lag = 0
    try:
        groups = await redis.xinfo_groups(settings.queue_stream)
        group = next((g for g in groups if g.get("name") == settings.queue_group), None)
        if group:
            pending = int(group.get("pending") or 0)
            lag = int(group.get("lag") or 0)
    except ResponseError:
        pass
    consumers: list[dict[str, Any]] = []
    try:
        consumers = [
            {
                "name": c.get("name"),
                "pending": int(c.get("pending") or 0),
                "idle_ms": int(c.get("idle") or 0),
            }
            for c in await redis.xinfo_consumers(settings.queue_stream, settings.queue_group)
        ]
    except ResponseError:
        pass
    return QueueStats(length=length, pending=pending, lag=lag, dlq=dlq, retry_zset=retry_len, consumers=consumers)


def new_trace_id() -> str:
    return __import__("secrets").token_hex(8)


def slot_of(dt: datetime) -> datetime:
    return ensure_utc(dt)
