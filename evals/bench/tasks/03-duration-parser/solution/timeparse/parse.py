import re

_PATTERN = re.compile(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")


def parse_duration(text: str) -> int:
    """Convert a duration such as "1h30m" or "90" to seconds."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    match = _PATTERN.fullmatch(text)
    if not text or match is None:
        raise ValueError(f"unsupported duration: {text!r}")
    days, hours, minutes, seconds = (int(group or 0) for group in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds
