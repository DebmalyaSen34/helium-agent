from payments import transport
from payments.errors import PaymentError


def charge(card_token: str, amount_cents: int) -> str:
    """Charge the card and return the provider's charge id."""
    try:
        response = transport.post("/charges", {"card": card_token, "amount": amount_cents})
        return response["id"]
    except Exception as exc:
        raise PaymentError(f"charge failed: {exc}") from exc
