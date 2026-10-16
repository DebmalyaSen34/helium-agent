from notify.sender import send


def raise_alert(service: str) -> dict:
    return send(f"ALERT: {service} is down", 5, 2.0)
