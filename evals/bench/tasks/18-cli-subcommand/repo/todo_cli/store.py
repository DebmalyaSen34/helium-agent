import json
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text())

    def save(self, tasks: list[dict]) -> None:
        self.path.write_text(json.dumps(tasks, indent=2))

    def add(self, title: str) -> dict:
        tasks = self.load()
        task = {"id": max((t["id"] for t in tasks), default=0) + 1, "title": title, "done": False}
        tasks.append(task)
        self.save(tasks)
        return task
