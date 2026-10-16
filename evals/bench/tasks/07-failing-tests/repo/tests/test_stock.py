import pytest

from inventory.errors import OutOfStock
from inventory.stock import Stock


def test_reserve_reduces_available():
    stock = Stock(10)
    stock.reserve(4)
    assert stock.available == 6


def test_cannot_reserve_more_than_available():
    stock = Stock(10)
    stock.reserve(8)
    with pytest.raises(OutOfStock):
        stock.reserve(3)


def test_release_never_goes_negative():
    stock = Stock(5)
    stock.reserve(2)
    stock.release(5)
    assert stock.reserved == 0
    assert stock.available == 5


def test_ship_removes_units_from_shelf():
    stock = Stock(10)
    stock.reserve(3)
    stock.ship(3)
    assert stock.on_hand == 7
    assert stock.reserved == 0
    assert stock.available == 7
