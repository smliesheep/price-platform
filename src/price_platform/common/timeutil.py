"""时间工具：时间槽推进、时区转换、RFC3339 编解码。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from croniter import croniter

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def truncate_second(dt: datetime) -> datetime:
    return ensure_utc(dt).replace(microsecond=0)


def to_rfc3339(dt: datetime) -> str:
    return ensure_utc(dt).isoformat()


def parse_rfc3339(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return ensure_utc(parsed)


def advance_next_run(
    *,
    schedule_type: str,
    interval_sec: int,
    cron_expr: str | None,
    slot: datetime,
    now: datetime,
) -> tuple[datetime, int]:
    """返回 (下次执行时间, 被跳过的时间槽数量)。

    - interval：保持相位，避免长期漂移；停机后只补最近一次。
    - cron：停机错过多次时，跳到 now 之后的下一次。
    """
    slot = ensure_utc(slot)
    now = ensure_utc(now)

    if schedule_type == "interval":
        if interval_sec <= 0:
            raise ValueError("interval_sec must be positive")
        delta = (now - slot).total_seconds()
        missed = max(0, int(delta // interval_sec))
        nxt = slot + timedelta(seconds=(missed + 1) * interval_sec)
        return nxt, max(0, missed)

    if not cron_expr:
        raise ValueError("cron_expr is required for schedule_type=cron")
    nxt = croniter(cron_expr, slot).get_next(datetime)
    nxt = ensure_utc(nxt)
    missed = 0
    if nxt <= now:
        nxt = ensure_utc(croniter(cron_expr, now).get_next(datetime))
        missed = 1
    return nxt, missed


def next_cron_after(expr: str, base: datetime) -> datetime:
    return ensure_utc(croniter(expr, ensure_utc(base)).get_next(datetime))
