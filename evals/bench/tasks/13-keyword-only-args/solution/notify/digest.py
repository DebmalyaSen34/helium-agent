from notify.sender import send


def daily_digest(items: list[str]) -> dict:
    body = "\n".join(f"- {item}" for item in items)
    return send(f"Daily digest\n{body}", retries=1, timeout=30.0)


def weekly_digest(items: list[str]) -> dict:
    return send("Weekly digest: " + ", ".join(items))
