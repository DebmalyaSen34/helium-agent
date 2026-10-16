import pytest

from inventory.errors import OutOfStock
from inventory.stock import Stock


def test_exact_remaining_can_be_reserved():
    stock = Stock(10)
    stock.reserve(7)
    stock.reserve(3)
    assert stock.available == 0
    with pytest.raises(OutOfStock):
        stock.reserve(1)


def test_release_clamps_at_zero():
    stock = Stock(3)
    stock.release(1)
    assert stock.reserved == 0


def test_ship_partial_reservation():
    stock = Stock(10)
    stock.reserve(5)
    stock.ship(2)
    assert (stock.on_hand, stock.reserved, stock.available) == (8, 3, 5)
