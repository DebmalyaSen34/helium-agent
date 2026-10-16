from dataclasses import dataclass, field


@dataclass
class Order:
    id: int
    status: str = "new"
    history: list[tuple[str, str]] = field(default_factory=list)
