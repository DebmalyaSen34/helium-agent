class TaskList:
    def __init__(self, name: str, tasks: list[str] | None = None, tags: set[str] | None = None):
        self.name = name
        self.tasks = tasks if tasks is not None else []
        self.tags = tags if tags is not None else set()

    def add(self, title: str) -> None:
        self.tasks.append(title)

    def tag(self, label: str) -> None:
        self.tags.add(label)

    def __len__(self) -> int:
        return len(self.tasks)
