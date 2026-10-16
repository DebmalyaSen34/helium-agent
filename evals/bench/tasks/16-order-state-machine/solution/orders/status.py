from orders.errors import InvalidTransition
from orders.model import Order

ALLOWED = {
    "new": {"paid", "cancelled"},
    "paid": {"shipped", "refunded"},
    "shipped": {"delivered"},
    "delivered": {"returned"},
}


def can_transition(order: Order, new_status: str) -> bool:
    return new_status in ALLOWED.get(order.status, set())


def transition(order: Order, new_status: str) -> Order:
    if not can_transition(order, new_status):
        raise InvalidTransition(f"cannot go from {order.status} to {new_status}")
    order.history.append((order.status, new_status))
    order.status = new_status
    return order
