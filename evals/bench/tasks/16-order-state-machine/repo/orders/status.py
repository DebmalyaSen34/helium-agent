from orders.model import Order


def can_transition(order: Order, new_status: str) -> bool:
    raise NotImplementedError


def transition(order: Order, new_status: str) -> Order:
    raise NotImplementedError
