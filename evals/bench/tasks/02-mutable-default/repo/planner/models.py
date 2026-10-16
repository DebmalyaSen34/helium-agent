class TaskList:
    def __init__(self, name: str, tasks: list[str] = [], tags: set[str] = set()):
        self.name = name
        self.tasks = tasks
        self.tags = tags

    def add(self, title: str) -> None:
        self.tasks.append(title)

    def tag(self, label: str) -> None:
        self.tags.add(label)

    def __len__(self) -> int:
        return len(self.tasks)
