import pytest

from dotenv_lite import parse

SAMPLE = """# database
export DB_HOST=localhost
DB_PORT = 5432
DB_PASS="p#ss word"   # quoted, so the # is part of the value
GREETING='hello "world"'
EMPTY=
URL=https://example.com/a#b  # unquoted: the comment starts at " #"
MULTI="line1\\nline2"
"""


def test_sample_file():
    assert parse(SAMPLE) == {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_PASS": "p#ss word",
        "GREETING": 'hello "world"',
        "EMPTY": "",
        "URL": "https://example.com/a#b",
        "MULTI": "line1\nline2",
    }


def test_single_quotes_are_literal():
    assert parse("A='x\\ny # z'") == {"A": "x\\ny # z"}


def test_inline_comment_needs_space():
    assert parse("A=b#c") == {"A": "b#c"}
    assert parse("A=b # c") == {"A": "b"}
    assert parse("A=b\t# c") == {"A": "b"}


def test_comment_after_quotes_and_empty_quotes():
    assert parse('A="" # nothing') == {"A": ""}


def test_later_keys_win():
    assert parse("A=1\nA=2") == {"A": "2"}


def test_missing_equals_reports_line():
    with pytest.raises(ValueError, match="3"):
        parse("A=1\n\nNOT A PAIR\n")
