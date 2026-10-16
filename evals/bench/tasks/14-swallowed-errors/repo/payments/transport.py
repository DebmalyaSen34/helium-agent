def post(path: str, payload: dict) -> dict:
    """Talk to the payment provider. Replaced in tests."""
    raise ConnectionError("no network in this environment")
