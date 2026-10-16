from notify.sender import send


def daily_digest(items: list[str]) -> dict:
    body = "\n".join(f"- {item}" for item in items)
    return send(f"Daily digest\n{body}", 1, 30.0)


def weekly_digest(items: list[str]) -> dict:
    return send("Weekly digest: " + ", ".join(items), 3, 10.0)
