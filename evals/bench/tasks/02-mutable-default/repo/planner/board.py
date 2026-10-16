from planner.models import TaskList


class Board:
    def __init__(self):
        self.lists: dict[str, TaskList] = {}

    def new_list(self, name: str) -> TaskList:
        self.lists[name] = TaskList(name)
        return self.lists[name]
