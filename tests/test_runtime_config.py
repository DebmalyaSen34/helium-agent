from __future__ import annotations

import os
import sys
from config.runtime_config import RuntimeConfigStore, parse_legacy_env_file


def test_env_values_override_stored_keyring_and_user_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    store = RuntimeConfigStore(config_path=config_path)
    store.save(
        api_key="stored-key",
        api_url="https://stored.example/v1",
        model="stored-model",
        use_playwright=False,
    )
    monkeypatch.setenv("LLM_API_KEY", "env-key")
    monkeypatch.setenv("LLM_API_URL", "https://env.example/v1")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    monkeypatch.setenv("USE_PLAYWRIGHT", "true")

    loaded = store.load()

    assert loaded.api_key == "env-key"
    assert loaded.api_url == "https://env.example/v1"
    assert loaded.model == "env-model"
    assert loaded.use_playwright is True
    assert loaded.sources == {
        "api_key": "env:LLM_API_KEY",
        "api_url": "env:LLM_API_URL",
        "model": "env:LLM_MODEL",
        "use_playwright": "env:USE_PLAYWRIGHT",
    }
    assert os.environ["LLM_API_KEY"] == "env-key"


def test_keyring_and_user_config_values_load_when_env_vars_are_absent(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("USE_PLAYWRIGHT", raising=False)
    config_path = tmp_path / "config.toml"
    store = RuntimeConfigStore(config_path=config_path)
    store.save(
        api_key="stored-key",
        api_url="https://stored.example/v1",
        model="stored-model",
        use_playwright=True,
    )

    loaded = store.load()

    assert loaded.api_key == "stored-key"
    assert loaded.api_url == "https://stored.example/v1"
    assert loaded.model == "stored-model"
    assert loaded.use_playwright is True
    assert loaded.is_complete is True
    assert loaded.sources == {
        "api_key": "user_config",
        "api_url": "user_config",
        "model": "user_config",
        "use_playwright": "user_config",
    }


def test_save_writes_secret_and_non_secret_values_to_config_toml(tmp_path):
    config_path = tmp_path / "nested" / "config.toml"
    store = RuntimeConfigStore(config_path=config_path)

    store.save(
        api_key="secret-key",
        api_url="https://api.example/v1",
        model="example-model",
        use_playwright=False,
    )

    assert config_path.exists()
    if sys.platform != "win32":
        assert (config_path.stat().st_mode & 0o777) == 0o600

    config_text = config_path.read_text()
    assert 'llm_api_key = "secret-key"' in config_text
    assert 'llm_api_url = "https://api.example/v1"' in config_text
    assert 'llm_model = "example-model"' in config_text
    assert 'use_playwright = false' in config_text


def test_parse_legacy_env_file_parses_llm_values(tmp_path):
    legacy_path = tmp_path / ".helium.env"
    legacy_path.write_text(
        "\n".join(
            [
                "LLM_API_KEY=legacy-key",
                "LLM_API_URL=https://legacy.example/v1",
                "LLM_MODEL=legacy-model",
                "USE_PLAYWRIGHT=false",
            ]
        )
    )

    parsed = parse_legacy_env_file(legacy_path)

    assert parsed == {
        "api_key": "legacy-key",
        "api_url": "https://legacy.example/v1",
        "model": "legacy-model",
        "use_playwright": False,
    }


def test_describe_status_does_not_return_secret_value(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "very-secret-key")
    monkeypatch.setenv("LLM_API_URL", "https://env.example/v1")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    store = RuntimeConfigStore(config_path=tmp_path / "config.toml")

    status = store.load().describe_status()

    assert status["api_key"]["present"] is True
    assert status["api_key"]["source"] == "env:LLM_API_KEY"
    assert "value" not in status["api_key"]
    assert "very-secret-key" not in repr(status)


def test_default_settings_do_not_depend_on_legacy_env_loader():
    import config.settings as settings

    assert hasattr(settings, "SETTINGS")
    assert not hasattr(settings, "GLOBAL_HELIUM_ENV")
