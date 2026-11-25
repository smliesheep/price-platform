from __future__ import annotations

from datetime import datetime, timezone

import pytest

from price_platform.common.queue import MessageFormatError, TaskMessage


def make_message() -> TaskMessage:
    return TaskMessage(
        run_id=42,
        task_id=7,
        product_id=7,
        source_id=1,
        slot_at=datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc),
        attempt=1,
        trace_id="abc123",
        enqueued_at=datetime(2026, 11, 25, 10, 0, 2, tzinfo=timezone.utc),
    )


def test_fields_roundtrip() -> None:
    msg = make_message()
    restored = TaskMessage.from_fields(msg.to_fields())
    assert restored == msg


def test_json_roundtrip() -> None:
    msg = make_message()
    assert TaskMessage.from_json(msg.to_json()) == msg


def test_missing_field_raises() -> None:
    fields = make_message().to_fields()
    del fields["run_id"]
    with pytest.raises(MessageFormatError):
        TaskMessage.from_fields(fields)


def test_unknown_version_raises() -> None:
    fields = make_message().to_fields()
    fields["v"] = "99"
    with pytest.raises(MessageFormatError):
        TaskMessage.from_fields(fields)


def test_next_attempt_increments() -> None:
    msg = make_message()
    nxt = msg.next_attempt(run_id=99)
    assert (nxt.attempt, nxt.run_id) == (2, 99)
    assert nxt.slot_at == msg.slot_at
