def parse(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("export "):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values
