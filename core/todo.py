from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4


class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class TodoItem:
    id: str
    title: str
    kind: str
    status: TodoStatus = TodoStatus.PENDING
    notes: list[str] = field(default_factory=list)


class TodoList:
    def __init__(self) -> None:
        self._items: list[TodoItem] = []
        self._by_id: dict[str, TodoItem] = {}

    def add(self, title: str, kind: str, notes: list[str] | None = None) -> TodoItem:
        item = TodoItem(
            id=self._new_id(),
            title=self._normalize(title),
            kind=self._normalize(kind),
            notes=list(notes or []),
        )
        self._items.append(item)
        self._by_id[item.id] = item
        return item

    def start(self, id: str) -> TodoItem:
        item = self._get(id)
        item.status = TodoStatus.IN_PROGRESS
        return item

    def complete(self, id: str, note: str | None = None) -> TodoItem:
        item = self._get(id)
        item.status = TodoStatus.COMPLETED
        if note is not None:
            item.notes.append(note)
        return item

    def block(self, id: str, reason: str) -> TodoItem:
        item = self._get(id)
        item.status = TodoStatus.BLOCKED
        item.notes.append(reason)
        return item

    def pending(self) -> list[TodoItem]:
        return self.by_status(TodoStatus.PENDING)

    def by_status(self, status: TodoStatus | str) -> list[TodoItem]:
        todo_status = TodoStatus(status)
        return [item for item in self._items if item.status == todo_status]

    def summary(self) -> dict[str, int]:
        counts = {status.value: len(self.by_status(status)) for status in TodoStatus}
        return {
            "total": len(self._items),
            **counts,
        }

    def _get(self, id: str) -> TodoItem:
        try:
            return self._by_id[id]
        except KeyError:
            raise KeyError(id) from None

    def _new_id(self) -> str:
        while True:
            id = uuid4().hex[:8]
            if id not in self._by_id:
                return id

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split())


__all__ = ["TodoItem", "TodoList", "TodoStatus"]
