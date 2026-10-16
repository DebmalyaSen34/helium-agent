from dataclasses import dataclass

from payments.errors import PaymentError
from payments.gateway import charge


@dataclass
class Order:
    id: int
    amount_cents: int
    status: str = "new"
    charge_id: str | None = None
    error: str | None = None


def checkout(order: Order, card_token: str) -> Order:
    try:
        order.charge_id = charge(card_token, order.amount_cents)
    except PaymentError as exc:
        order.status = "payment_failed"
        order.error = str(exc)
        return order
    order.status = "paid"
    return order
