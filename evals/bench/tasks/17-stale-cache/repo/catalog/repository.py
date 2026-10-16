from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    price_cents: int


class Repository:
    """Stands in for a database; counts queries so callers can see the cost."""

    def __init__(self, products: list[Product]):
        self._rows = {p.id: p for p in products}
        self.queries = 0

    def get(self, product_id: int) -> Product:
        self.queries += 1
        return self._rows[product_id]

    def all(self) -> list[Product]:
        self.queries += 1
        return sorted(self._rows.values(), key=lambda p: p.id)

    def set_price(self, product_id: int, price_cents: int) -> None:
        self.queries += 1
        self._rows[product_id] = replace(self._rows[product_id], price_cents=price_cents)
