import json
from datetime import datetime
from decimal import Decimal

from events.model import Event
from events.serialize import to_json


def test_to_json_is_json():
    event = Event("signup", datetime(2024, 1, 2, 3, 4, 5), Decimal("1"))
    assert json.loads(to_json(event))["name"] == "signup"
