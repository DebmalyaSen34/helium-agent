from decimal import Decimal

from billing.totals import compute_total


class Invoice:
    def __init__(self, customer: str, region: str = "default"):
        self.customer = customer
        self.region = region
        self.lines: list[tuple[str, Decimal, int]] = []

    def add(self, description: str, unit_price: str, quantity: int = 1) -> None:
        self.lines.append((description, Decimal(unit_price), quantity))

    def total(self) -> Decimal:
        return compute_total(self.lines, self.region)
