from notify.sender import send


def run() -> list[dict]:
    results = []
    for job in ("backup", "reindex"):
        results.append(send(f"nightly {job} finished", 0, 60.0))
    return results
