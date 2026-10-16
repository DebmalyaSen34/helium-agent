import argparse
import sys

from wordcount.counting import count_words


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wordcount", description="Count words in a file.")
    parser.add_argument("path", help="file to read, or - for stdin")
    parser.add_argument("--top", type=int, default=10, help="how many words to show")
    parser.add_argument("--reverse", action="store_true", help="list the least common words first")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    text = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
    counts = count_words(text)
    direction = 1 if args.reverse else -1
    ranked = sorted(counts.items(), key=lambda item: (direction * item[1], item[0]))
    for word, count in ranked[: args.top]:
        print(f"{word} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
