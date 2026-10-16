def send(message: str, *, retries: int = 3, timeout: float = 10.0) -> dict:
    """Deliver `message` (the transport is stubbed out; this returns what would be sent)."""
    if retries < 0 or timeout <= 0:
        raise ValueError("retries must be >= 0 and timeout > 0")
    return {"message": message, "retries": retries, "timeout": timeout}
