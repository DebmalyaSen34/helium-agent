import pytest


@pytest.fixture(autouse=True)
def _no_real_llm_requests(monkeypatch):
    """Fail fast if a test would reach a real LLM endpoint."""

    def blocked(*args, **kwargs):
        raise RuntimeError("Real LLM HTTP requests are disabled in tests; patch hit_api or the model.")

    monkeypatch.setattr("utils.check_llm_api.requests.post", blocked)
