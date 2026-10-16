from orders.model import Order
from orders.status import transition


def fulfil(order: Order) -> Order:
    """Pay, ship, and deliver an order."""
    for status in ("paid", "shipped", "delivered"):
        transition(order, status)
    return order
