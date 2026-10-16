from decimal import Decimal

from billing import compute_total


def test_total_includes_tax():
    assert compute_total([("widget", Decimal("10.00"), 2)], "eu") == Decimal("24.00")
