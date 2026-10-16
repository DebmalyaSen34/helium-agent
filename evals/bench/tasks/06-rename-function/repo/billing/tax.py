from decimal import Decimal

RATES = {"default": Decimal("0.10"), "eu": Decimal("0.20"), "none": Decimal("0")}


def tax_for(amount: Decimal, region: str) -> Decimal:
    return amount * RATES.get(region, RATES["default"])
