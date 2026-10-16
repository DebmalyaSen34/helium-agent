import inspect

import pytest

from notify import alerts, digest
from notify.sender import send
from scripts import nightly


def test_signature_is_keyword_only_with_defaults():
    params = inspect.signature(send).parameters
    assert params["retries"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["timeout"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["retries"].default == 3
    assert params["timeout"].default == 10.0
    with pytest.raises(TypeError):
        send("x", 1, 2.0)


def test_defaults():
    assert send("x") == {"message": "x", "retries": 3, "timeout": 10.0}


def test_callers_keep_their_values():
    assert alerts.raise_alert("db")["retries"] == 5
    assert alerts.raise_alert("db")["timeout"] == 2.0
    daily = digest.daily_digest(["a"])
    assert (daily["retries"], daily["timeout"]) == (1, 30.0)
    weekly = digest.weekly_digest(["a", "b"])
    assert (weekly["retries"], weekly["timeout"]) == (3, 10.0)
    assert [(r["retries"], r["timeout"]) for r in nightly.run()] == [(0, 60.0), (0, 60.0)]
