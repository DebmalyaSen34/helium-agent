import pytest

from signup.validate import validate_signup
from signup.views import handle_signup

GOOD = {"email": "ada@example.com", "password": "correct1horse"}


def test_valid():
    assert validate_signup(GOOD) == []
    assert validate_signup({**GOOD, "age": 36}) == []


@pytest.mark.parametrize("email", ["", "   ", None])
def test_email_required(email):
    assert validate_signup({**GOOD, "email": email}) == ["email is required"]


@pytest.mark.parametrize("email", ["ada", "@example.com", "ada@", "ada@example", "a@b@c.com", "ada@.com", "ada@example."])
def test_invalid_email(email):
    assert validate_signup({**GOOD, "email": email}) == ["invalid email"]


def test_password_rules():
    assert validate_signup({**GOOD, "password": "short1"}) == ["password too short"]
    assert validate_signup({**GOOD, "password": "longenough"}) == ["password needs a digit"]
    assert validate_signup({**GOOD, "password": "abc"}) == ["password too short", "password needs a digit"]
    assert validate_signup({"email": GOOD["email"]}) == ["password too short", "password needs a digit"]


@pytest.mark.parametrize("age", [12, 121, "30", 30.5, True])
def test_invalid_age(age):
    assert validate_signup({**GOOD, "age": age}) == ["invalid age"]


@pytest.mark.parametrize("age", [13, 120])
def test_age_bounds(age):
    assert validate_signup({**GOOD, "age": age}) == []


def test_order_of_all_errors():
    assert validate_signup({"email": "nope", "password": "x", "age": 5}) == [
        "invalid email", "password too short", "password needs a digit", "invalid age",
    ]


def test_view_accepts_valid_form():
    assert handle_signup({**GOOD, "email": " Ada@Example.com "})[0] == 201
