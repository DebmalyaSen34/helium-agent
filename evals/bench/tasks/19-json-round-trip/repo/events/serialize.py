import json
from dataclasses import asdict

from events.model import Event


def to_json(event: Event) -> str:
    data = asdict(event)
    data["at"] = event.at.isoformat()
    data["amount"] = float(event.amount)
    data["tags"] = list(event.tags)
    return json.dumps(data)


def from_json(text: str) -> Event:
    return Event(**json.loads(text))
