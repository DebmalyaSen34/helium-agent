from dataclasses import dataclass

from payments.gateway import charge


@dataclass
class Order:
    id: int
    amount_cents: int
    status: str = "new"
    charge_id: str | None = None
    error: str | None = None


def checkout(order: Order, card_token: str) -> Order:
    order.charge_id = charge(card_token, order.amount_cents)
    order.status = "paid"
    return order
