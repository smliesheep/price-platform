from __future__ import annotations

from datetime import datetime, timedelta, timezone

from price_platform.common.timeutil import advance_next_run, parse_rfc3339, to_rfc3339

UTC = timezone.utc


def test_interval_keeps_phase_and_counts_missed() -> None:
    now = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
    slot = now - timedelta(seconds=7200)  # 落后 4 个周期
    nxt, missed = advance_next_run(
        schedule_type="interval", interval_sec=1800, cron_expr=None, slot=slot, now=now
    )
    assert missed == 4
    assert nxt == slot + timedelta(seconds=5 * 1800)
    assert nxt > now


def test_interval_without_backlog() -> None:
    now = datetime(2026, 11, 25, 11, 30, 10, tzinfo=UTC)
    slot = datetime(2026, 11, 25, 11, 30, 0, tzinfo=UTC)
    nxt, missed = advance_next_run(
        schedule_type="interval", interval_sec=1800, cron_expr=None, slot=slot, now=now
    )
    assert missed == 0
    assert nxt == datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
    assert nxt - slot == timedelta(seconds=1800)


def test_cron_next_occurrence() -> None:
    slot = datetime(2026, 11, 25, 10, 5, 0, tzinfo=UTC)
    now = datetime(2026, 11, 25, 10, 6, 0, tzinfo=UTC)
    nxt, missed = advance_next_run(
        schedule_type="cron", interval_sec=0, cron_expr="*/30 * * * *", slot=slot, now=now
    )
    assert missed == 0
    assert nxt == datetime(2026, 11, 25, 10, 30, 0, tzinfo=UTC)


def test_cron_after_long_downtime_jumps_forward() -> None:
    slot = datetime(2026, 11, 20, 10, 0, 0, tzinfo=UTC)
    now = datetime(2026, 11, 25, 10, 6, 0, tzinfo=UTC)
    nxt, missed = advance_next_run(
        schedule_type="cron", interval_sec=0, cron_expr="*/30 * * * *", slot=slot, now=now
    )
    assert missed >= 1
    assert nxt > now


def test_rfc3339_roundtrip() -> None:
    moment = datetime(2026, 11, 25, 12, 30, 0, 123456, tzinfo=UTC)
    text = to_rfc3339(moment)
    assert parse_rfc3339(text) == moment.replace(microsecond=123456)

