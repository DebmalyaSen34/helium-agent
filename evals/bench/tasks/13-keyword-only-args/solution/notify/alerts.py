from notify.sender import send


def raise_alert(service: str) -> dict:
    return send(f"ALERT: {service} is down", retries=5, timeout=2.0)
