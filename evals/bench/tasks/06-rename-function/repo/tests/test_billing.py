from decimal import Decimal

from billing import calc_total


def test_total_includes_tax():
    assert calc_total([("widget", Decimal("10.00"), 2)], "eu") == Decimal("24.00")
