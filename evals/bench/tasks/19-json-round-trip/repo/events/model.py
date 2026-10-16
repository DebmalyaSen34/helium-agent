from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Event:
    name: str
    at: datetime
    amount: Decimal
    tags: frozenset[str] = field(default_factory=frozenset)
    note: str | None = None
