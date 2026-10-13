import pytest


@pytest.fixture(autouse=True)
def _no_real_llm_requests(request, monkeypatch):
    """Fail fast if a test would reach a real LLM endpoint (except opt-in live tests)."""
    if request.node.get_closest_marker("live"):
        return

    def blocked(*args, **kwargs):
        raise RuntimeError("Real LLM HTTP requests are disabled in tests; patch hit_api or the model.")

    monkeypatch.setattr("utils.check_llm_api.requests.post", blocked)


@pytest.fixture(autouse=True)
def _isolated_user_data(tmp_path, monkeypatch):
    """Keep per-workspace memory and history out of the real user data directory."""
    monkeypatch.setenv("HELIUM_DATA_DIR", str(tmp_path / "helium-data"))


def pytest_configure(config):
    config.addinivalue_line("markers", "live: calls a real LLM API; opt in with HELIUM_LIVE_DEEPSEEK=1")
