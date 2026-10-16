import argparse
import sys
from pathlib import Path

from todo_cli.store import Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo")
    parser.add_argument("--db", type=Path, default=Path("todo.json"))
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="add a task")
    add.add_argument("title")

    listing = commands.add_parser("list", help="list tasks")
    listing.add_argument("--pending", action="store_true", help="only show tasks that aren't done")

    done = commands.add_parser("done", help="mark a task as done")
    done.add_argument("id", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(args.db)

    if args.command == "add":
        task = store.add(args.title)
        print(f"Added {task['id']}: {task['title']}")
    elif args.command == "list":
        for task in store.load():
            if args.pending and task["done"]:
                continue
            mark = "x" if task["done"] else " "
            print(f"[{mark}] {task['id']} {task['title']}")
    elif args.command == "done":
        tasks = store.load()
        task = next((t for t in tasks if t["id"] == args.id), None)
        if task is None:
            print(f"No task {args.id}", file=sys.stderr)
            return 1
        task["done"] = True
        store.save(tasks)
        print(f"Completed {task['id']}: {task['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
