from dotenv_lite import parse


def test_simple():
    assert parse("A=1\n# c\n\nB = two") == {"A": "1", "B": "two"}
