from app.client import HttpClient
from app.config import load_config
from app.main import build_client


def test_default_timeout_comes_from_config(monkeypatch):
    monkeypatch.delenv("APP_TIMEOUT_SECONDS", raising=False)
    assert build_client().timeout == 30


def test_env_timeout_is_applied(monkeypatch):
    monkeypatch.setenv("APP_TIMEOUT_SECONDS", "60")
    client = build_client()
    assert client.timeout == 60
    assert "timeout=60s" in client.describe()


def test_explicit_config():
    assert HttpClient(load_config({"APP_TIMEOUT_SECONDS": "7"})).timeout == 7
