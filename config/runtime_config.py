from __future__ import annotations

import os

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 fallback
    try:
        import tomli as tomllib
    except ModuleNotFoundError:  # pragma: no cover
        tomllib = None

try:
    from platformdirs import user_config_dir
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    user_config_dir = None


APP_NAME = "helium-agent"
LEGACY_ENV_PATH = Path.home() / ".helium.env"


class RuntimeConfigError(Exception):
    """Raised when runtime configuration cannot be securely loaded or saved."""


@dataclass
class LlmRuntimeConfig:
    api_key: str | None
    api_url: str | None
    model: str | None
    use_playwright: bool | None
    sources: dict[str, str]

    @property
    def is_complete(self) -> bool:
        return bool(self.api_key and self.api_url and self.model)

    def describe_status(self) -> dict[str, Any]:
        fields = {
            "api_key": self.api_key,
            "api_url": self.api_url,
            "model": self.model,
            "use_playwright": self.use_playwright,
        }
        status: dict[str, Any] = {
            name: {
                "present": value is not None and value != "",
                "source": self.sources.get(name),
            }
            for name, value in fields.items()
        }
        status["is_complete"] = self.is_complete
        return status


def default_user_config_path() -> Path:
    if user_config_dir is None:
        return Path.home() / ".config" / APP_NAME / "config.toml"
    return Path(user_config_dir(APP_NAME)) / "config.toml"


def _coerce_bool(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_legacy_env_file(path: Path = LEGACY_ENV_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}

    values = dotenv_values(path)
    parsed: dict[str, Any] = {}
    key = _clean_string(values.get("LLM_API_KEY"))
    api_url = _clean_string(values.get("LLM_API_URL"))
    model = _clean_string(values.get("LLM_MODEL"))
    use_playwright = _coerce_bool(values.get("USE_PLAYWRIGHT"))

    if key is not None:
        parsed["api_key"] = key
    if api_url is not None:
        parsed["api_url"] = api_url
    if model is not None:
        parsed["model"] = model
    if use_playwright is not None:
        parsed["use_playwright"] = use_playwright
    return parsed


class RuntimeConfigStore:
    def __init__(
        self,
        config_path: Path | None = None,
        legacy_env_path: Path = LEGACY_ENV_PATH,
    ) -> None:
        self.config_path = config_path or default_user_config_path()
        self.legacy_env_path = legacy_env_path

    def load(self, include_legacy: bool = False) -> LlmRuntimeConfig:
        user_config = self._read_user_config()
        loaded = {
            "api_key": None,
            "api_url": None,
            "model": None,
            "use_playwright": None,
        }
        sources: dict[str, str] = {}

        self._apply_env(loaded, sources)
        self._apply_user_config(loaded, sources, user_config)
        if include_legacy:
            self._apply_legacy(loaded, sources)

        return LlmRuntimeConfig(
            api_key=loaded["api_key"],
            api_url=loaded["api_url"],
            model=loaded["model"],
            use_playwright=loaded["use_playwright"],
            sources=sources,
        )

    def save(
        self,
        api_key: str | None,
        api_url: str | None,
        model: str | None,
        use_playwright: bool | None,
    ) -> None:
        values: dict[str, Any] = {}
        if api_key is not None:
            values["llm_api_key"] = api_key
        if api_url is not None:
            values["llm_api_url"] = api_url
        if model is not None:
            values["llm_model"] = model
        if use_playwright is not None:
            values["use_playwright"] = bool(use_playwright)
        self._write_user_config(values)

    def import_legacy(self) -> LlmRuntimeConfig:
        legacy_values = parse_legacy_env_file(self.legacy_env_path)
        self.save(
            api_key=legacy_values.get("api_key"),
            api_url=legacy_values.get("api_url"),
            model=legacy_values.get("model"),
            use_playwright=legacy_values.get("use_playwright"),
        )
        return self.load()

    def _read_user_config(self) -> dict[str, Any]:
        if not self.config_path.exists() or tomllib is None:
            return {}
        with self.config_path.open("rb") as config_file:
            return tomllib.load(config_file)

    def _write_user_config(self, values: dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            fd = os.open(self.config_path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
        else:
            try:
                self.config_path.chmod(0o600)
            except OSError:  # pragma: no cover
                pass
        lines = [f"{name} = {_toml_value(value)}" for name, value in values.items()]
        text = "\n".join(lines)
        if text:
            text += "\n"
        self.config_path.write_text(text)

    def _apply_user_config(
        self,
        loaded: dict[str, Any],
        sources: dict[str, str],
        user_config: dict[str, Any],
    ) -> None:
        field_map = {
            "api_key": "llm_api_key",
            "api_url": "llm_api_url",
            "model": "llm_model",
            "use_playwright": "use_playwright",
        }
        for field, config_key in field_map.items():
            value = user_config.get(config_key)
            if field == "use_playwright":
                value = _coerce_bool(value)
            else:
                value = _clean_string(value)
            if value is not None and loaded.get(field) is None:
                loaded[field] = value
                sources[field] = "user_config"

    def _apply_legacy(self, loaded: dict[str, Any], sources: dict[str, str]) -> None:
        legacy_values = parse_legacy_env_file(self.legacy_env_path)
        for field, value in legacy_values.items():
            if loaded.get(field) is None:
                loaded[field] = value
                sources[field] = "legacy_env"

    def _apply_env(self, loaded: dict[str, Any], sources: dict[str, str]) -> None:
        env_map = {
            "api_key": "LLM_API_KEY",
            "api_url": "LLM_API_URL",
            "model": "LLM_MODEL",
            "use_playwright": "USE_PLAYWRIGHT",
        }
        for field, env_name in env_map.items():
            value: Any
            if field == "use_playwright":
                value = _coerce_bool(os.environ.get(env_name))
            else:
                value = _clean_string(os.environ.get(env_name))
            if value is not None:
                loaded[field] = value
                sources[field] = f"env:{env_name}"


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return f"\"{str(value).replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}\""


def load_llm_runtime_config(include_legacy: bool = False) -> LlmRuntimeConfig:
    return RuntimeConfigStore().load(include_legacy=include_legacy)


def save_llm_runtime_config(
    api_key: str | None,
    api_url: str | None,
    model: str | None,
    use_playwright: bool | None,
) -> None:
    RuntimeConfigStore().save(api_key, api_url, model, use_playwright)


def import_legacy_runtime_config() -> LlmRuntimeConfig:
    return RuntimeConfigStore().import_legacy()


def describe_llm_config_status(include_legacy: bool = False) -> dict[str, Any]:
    return load_llm_runtime_config(include_legacy=include_legacy).describe_status()
