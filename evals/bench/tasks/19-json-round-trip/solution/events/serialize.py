import json
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from events.model import Event


def to_json(event: Event) -> str:
    data = asdict(event)
    data["at"] = event.at.isoformat()
    data["amount"] = str(event.amount)
    data["tags"] = sorted(event.tags)
    return json.dumps(data, sort_keys=True)


def from_json(text: str) -> Event:
    data = json.loads(text)
    data["at"] = datetime.fromisoformat(data["at"])
    data["amount"] = Decimal(data["amount"])
    data["tags"] = frozenset(data["tags"])
    return Event(**data)
