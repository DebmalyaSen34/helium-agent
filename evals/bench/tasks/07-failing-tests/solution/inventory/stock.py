from inventory.errors import OutOfStock


class Stock:
    """Tracks units on hand and units reserved for unpaid orders."""

    def __init__(self, on_hand: int = 0):
        self.on_hand = on_hand
        self.reserved = 0

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved

    def reserve(self, qty: int) -> None:
        if qty > self.available:
            raise OutOfStock(f"only {self.available} available")
        self.reserved += qty

    def release(self, qty: int) -> None:
        self.reserved = max(0, self.reserved - qty)

    def ship(self, qty: int) -> None:
        """Ship reserved units: they leave both the reservation and the shelf."""
        self.reserved -= qty
        self.on_hand -= qty
