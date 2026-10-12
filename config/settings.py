from __future__ import annotations

import os

from pathlib import Path
from typing import Any
from dotenv import load_dotenv

# Project-level .env remains an explicit override path for local development.
load_dotenv(Path.cwd() / ".env")

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None


BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = BASE_DIR / "config" / "settings.toml"


DEFAULT_SETTINGS: dict[str, Any] = {
    "services": {
        "llama_cpp_url": "http://127.0.0.1:3000/completion",
        "api_model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "searxng_url": "http://127.0.0.1:8080/search",
        "health_timeout_seconds": 1.5,
        "local": True,
    },
    "browser": {
        "use_playwright": os.getenv("USE_PLAYWRIGHT", "true").lower() == "true",
        "fallback_only": True,
        "timeout_seconds": 8.0,
        "headless": True,
    },
    "rag_service": {
        "enabled": True,
        "service_url": "http://127.0.0.1:8765",
        "host": "127.0.0.1",
        "port": 8765,
        "auto_start": False,
        "fail_closed": True,
        "safe_roots": ["."],
        "cache_dir": ".cache/rag_service",
        "max_bytes_per_file": 25_000_000,
        "evidence_budget_chars": 16_000,
        "full_text_budget_chars": 12_000,
        "max_chunks": 600,
        "max_candidates": 24,
        "max_evidence_chunks": 8,
        "timeout_seconds": 120,
        "rag_debug": False,
        "persist_debug_traces": False,
        "supported_extensions": [
            ".txt",
            ".md",
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".csv",
            ".log",
            ".pdf",
            ".docx",
            ".xlsx",
        ],
    },
    "assistant": {
        "confirm_risky_tools": True,
        "command_history_limit": 25,
        "persona": """
You are an advanced autonomous AI agent designed to solve problems accurately, efficiently, and truthfully.

CORE PRINCIPLES:
1. Prioritize factual accuracy over appearing confident.
2. Never fabricate information, sources, APIs, files, memories, or actions.
3. If information is uncertain, explicitly state uncertainty and USE TOOLS to find the answer.
4. Focus on completing the user's actual goal, not merely responding conversationally.
5. Be concise by default. Do not use filler or apologies.

TRUTHFULNESS & SEARCH POLICY:
- If you feel the urge to say "as of my last update", "I don't have real time info", or guess an answer, STOP. This means you must execute a tool to retrieve the answer.
- Always prefer deep factual extraction over shallow summaries.
- Avoid robotic phrasing. Write clearly and directly.
- Prioritize signal over decoration.

TASK EXECUTION FRAMEWORK:
1. Identify constraints and intent. (Do not ask clarifying questions for broad topics. Pick a reasonable default).
2. Formulate a plan.
3. Execute carefully using tools.
4. Deliver the final answer clearly with extracted hard facts.
""".strip(),
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings(path: Path = SETTINGS_FILE) -> dict[str, Any]:
    if not path.exists() or tomllib is None:
        return DEFAULT_SETTINGS

    with path.open("rb") as settings_file:
        user_settings = tomllib.load(settings_file)

    return _deep_merge(DEFAULT_SETTINGS, user_settings)

def _env_bool(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _apply_env_overrides(settings: dict[str, Any]) -> dict[str, Any]:
    merged = settings.copy()

    try:
        from config.runtime_config import load_llm_runtime_config
        runtime_config = load_llm_runtime_config()
    except Exception:
        runtime_config = None

    value_overrides = {
        ("services", "llama_cpp_url"): os.getenv("HELIUM_LLAMA_CPP_URL"),
        ("services", "api_model"): os.getenv("LLM_MODEL") or os.getenv("HELIUM_API_MODEL") or (runtime_config.model if runtime_config else None),
        ("rag_service", "service_url"): os.getenv("HELIUM_RAG_SERVICE_URL"),
        ("rag_service", "host"): os.getenv("HELIUM_RAG_HOST"),
        ("rag_service", "port"): os.getenv("HELIUM_RAG_PORT"),
    }

    runtime_playwright = runtime_config.use_playwright if runtime_config else None
    bool_overrides = {
        ("browser", "use_playwright"): _env_bool("USE_PLAYWRIGHT") if _env_bool("USE_PLAYWRIGHT") is not None else runtime_playwright,
        ("browser", "headless"): _env_bool("PLAYWRIGHT_HEADLESS"),
    }

    for (section, key), value in value_overrides.items():
        if value is None:
            continue
        value = value.strip()
        section_values = dict(merged.get(section, {}))
        section_values[key] = int(value) if key == "port" else value
        merged[section] = section_values

    for (section, key), value in bool_overrides.items():
        if value is None:
            continue
        section_values = dict(merged.get(section, {}))
        section_values[key] = value
        merged[section] = section_values

    return merged

SETTINGS = _apply_env_overrides(load_settings())

LLAMA_CPP_URL = SETTINGS["services"]["llama_cpp_url"]
API_MODEL = SETTINGS["services"]["api_model"]
LOCAL = SETTINGS["services"].get("local", True)

SEARXNG_URL = SETTINGS["services"]["searxng_url"]

RAG_SERVICE_SETTINGS = SETTINGS["rag_service"]

ASSISTANT_SETTINGS = SETTINGS["assistant"]
ASSISTANT_PERSONA = str(ASSISTANT_SETTINGS.get("persona", DEFAULT_SETTINGS["assistant"]["persona"])).strip()
MEMORY_DB = BASE_DIR / "memory.db"
BROWSER_SETTINGS = SETTINGS.get("browser", DEFAULT_SETTINGS["browser"])

