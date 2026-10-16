import pytest

from fmt.box import box
from fmt.wrap import wrap


def test_breaks_at_spaces():
    assert wrap("the quick brown fox jumps", 10) == ["the quick", "brown fox", "jumps"]


def test_collapses_whitespace():
    assert wrap("  a   b\n\nc\td  ", 3) == ["a b", "c d"]


def test_exact_fit():
    assert wrap("abc def", 7) == ["abc def"]
    assert wrap("abc def", 3) == ["abc", "def"]


def test_long_words_are_split():
    assert wrap("supercalifragilistic ok", 8) == ["supercal", "ifragili", "stic ok"]


def test_empty():
    assert wrap("", 5) == []
    assert wrap("   \n ", 5) == []


@pytest.mark.parametrize("width", [0, -3])
def test_invalid_width(width):
    with pytest.raises(ValueError):
        wrap("text", width)


def test_no_line_exceeds_width():
    text = "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor"
    for width in range(1, 30):
        lines = wrap(text, width)
        assert all(0 < len(line) <= width for line in lines)
        assert "".join(lines).replace(" ", "") == text.replace(" ", "")


def test_box():
    assert box("hello world", 5).splitlines() == ["+-------+", "| hello |", "| world |", "+-------+"]
