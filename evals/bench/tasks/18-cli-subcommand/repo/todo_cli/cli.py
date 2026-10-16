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

    commands.add_parser("list", help="list tasks")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(args.db)

    if args.command == "add":
        task = store.add(args.title)
        print(f"Added {task['id']}: {task['title']}")
    elif args.command == "list":
        for task in store.load():
            print(f"[ ] {task['id']} {task['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
