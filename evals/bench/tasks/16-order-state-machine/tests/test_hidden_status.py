import pytest

from orders.errors import InvalidTransition
from orders.model import Order
from orders.service import fulfil
from orders.status import can_transition, transition

ALLOWED = {
    ("new", "paid"), ("new", "cancelled"), ("paid", "shipped"), ("paid", "refunded"),
    ("shipped", "delivered"), ("delivered", "returned"),
}
STATUSES = ["new", "paid", "cancelled", "shipped", "refunded", "delivered", "returned"]


@pytest.mark.parametrize("old", STATUSES)
@pytest.mark.parametrize("new", STATUSES + ["lost"])
def test_every_pair(old, new):
    order = Order(1, status=old)
    assert can_transition(order, new) == ((old, new) in ALLOWED)
    assert order.status == old
    if (old, new) in ALLOWED:
        assert transition(order, new) is order
        assert order.status == new
        assert order.history == [(old, new)]
    else:
        with pytest.raises(InvalidTransition, match=f"cannot go from {old} to {new}"):
            transition(order, new)
        assert order.status == old
        assert order.history == []


def test_fulfil_records_history():
    order = fulfil(Order(7))
    assert order.status == "delivered"
    assert order.history == [("new", "paid"), ("paid", "shipped"), ("shipped", "delivered")]
