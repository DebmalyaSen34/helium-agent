from decimal import Decimal

from billing.tax import tax_for


def compute_total(lines: list[tuple[str, Decimal, int]], region: str = "default") -> Decimal:
    """Total for invoice lines of (description, unit_price, quantity), including tax."""
    subtotal = sum((price * qty for _, price, qty in lines), Decimal("0"))
    return (subtotal + tax_for(subtotal, region)).quantize(Decimal("0.01"))
