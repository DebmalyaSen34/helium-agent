from decimal import Decimal

from sales.render import render


def test_render_orders_by_amount():
    assert render({"b": Decimal("1"), "a": Decimal("2")}) == "a: 2\nb: 1"
