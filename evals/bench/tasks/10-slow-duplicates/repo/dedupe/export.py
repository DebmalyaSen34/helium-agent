import csv

from dedupe.finder import find_duplicates


def duplicate_emails(path: str) -> list[str]:
    with open(path, newline="", encoding="utf-8") as handle:
        emails = [row["email"].strip().lower() for row in csv.DictReader(handle)]
    return find_duplicates(emails)
