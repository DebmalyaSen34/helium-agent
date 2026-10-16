from collections import defaultdict
from decimal import Decimal


def parse_amount(text: str) -> Decimal:
    """Amounts look like "1,200.50" or "99"."""
    return Decimal(text.replace(",", ""))


def summarize(rows: list[dict]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        totals[row["region"]] += parse_amount(row["amount"])
    return dict(totals)
