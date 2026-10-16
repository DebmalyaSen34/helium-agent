def wrap(text: str, width: int) -> list[str]:
    """Wrap `text` into lines of at most `width` characters."""
    return [text[i:i + width] for i in range(0, len(text), width)]
