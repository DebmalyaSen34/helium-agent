import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from events.model import Event
from events.serialize import from_json, to_json

EVENTS = [
    Event("signup", datetime(2024, 1, 2, 3, 4, 5), Decimal("0")),
    Event("purchase", datetime(2024, 5, 6, 7, 8, 9, 123456, tzinfo=timezone.utc), Decimal("0.10"), frozenset({"vip", "eu"})),
    Event("refund", datetime(2023, 12, 31, 23, 59, tzinfo=timezone(timedelta(hours=5, minutes=30))), Decimal("-1234567.891"), note="late"),
    Event("tiny", datetime(2020, 2, 29), Decimal("1E-10"), frozenset(), note=""),
]


@pytest.mark.parametrize("event", EVENTS, ids=lambda e: e.name)
def test_round_trip(event):
    text = to_json(event)
    json.loads(text)
    restored = from_json(text)
    assert restored == event
    assert type(restored.amount) is Decimal
    assert str(restored.amount) == str(event.amount)
    assert restored.at.tzinfo == event.at.tzinfo
    assert isinstance(restored.tags, frozenset)


def test_output_is_deterministic():
    event = EVENTS[1]
    assert to_json(event) == to_json(Event(event.name, event.at, event.amount, frozenset(sorted(event.tags))))
