import pytest

from timeparse import parse_duration
from timeparse.format import format_duration


@pytest.mark.parametrize("text, seconds", [
    ("30s", 30),
    ("90", 90),
    ("1h30m", 5400),
    ("2d", 172800),
    ("45m10s", 2710),
    ("1d2h3m4s", 93784),
    (" 15m ", 900),
    ("0s", 0),
])
def test_valid(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "5x", "h", "10m5h", "1h1h", "-5s", "1.5h", "abc"])
def test_invalid(text):
    with pytest.raises(ValueError):
        parse_duration(text)


@pytest.mark.parametrize("seconds", [1, 59, 61, 3600, 5400, 93784, 172800])
def test_round_trip_with_format(seconds):
    assert parse_duration(format_duration(seconds)) == seconds
