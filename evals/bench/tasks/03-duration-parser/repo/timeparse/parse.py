def parse_duration(text: str) -> int:
    """Convert a duration such as "30s" to seconds."""
    text = text.strip()
    if text.endswith("s") and text[:-1].isdigit():
        return int(text[:-1])
    raise ValueError(f"unsupported duration: {text!r}")
