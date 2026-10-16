from payments import transport


def charge(card_token: str, amount_cents: int) -> str | None:
    """Charge the card and return the provider's charge id."""
    try:
        response = transport.post("/charges", {"card": card_token, "amount": amount_cents})
        return response["id"]
    except Exception:
        return None
