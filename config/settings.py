from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    tomllib = None


BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = BASE_DIR / "config" / "settings.toml"


DEFAULT_SETTINGS: dict[str, Any] = {
    "services": {
        "llama_cpp_url": "http://127.0.0.1:3000/completion",
        "ollama_url": "http://127.0.0.1:11434/api/generate",
        "ollama_model": "gemma4:e2b",
        "api_model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "searxng_url": "http://127.0.0.1:8080/search",
        "health_timeout_seconds": 1.5,
        "local": True,
    },
    "browser": {
        "use_playwright": True,
        "fallback_only": True,
        "timeout_seconds": 8.0,
        "headless": True,
    },
    "wake_word": {
        "models": ["jarvis"],
        "threshold": 0.35,
        "smoothing_window": 4,
        "required_hits": 2,
        "cooldown_seconds": 1.2,
        "sample_rate": 16000,
        "frame_size": 1280,
        "debug": True,
        "push_to_talk": True,
        "push_to_talk_key": "enter",
        "calibration_seconds": 1.5,
        "microphone_device_index": -1,
    },
    "speech": {
        "whisper_model": "mlx-community/whisper-small-mlx",
        "initial_prompt": "Jarvis voice assistant commands. Transcribe concise spoken user requests accurately.",
        "sample_rate": 16000,
        "timeout_seconds": 8,
        "phrase_time_limit_seconds": 30,
        "follow_up_timeout_seconds": 6,
        "retry_attempts": 1,
        "ambient_noise_seconds": 0.5,
        "energy_threshold": 300,
        "dynamic_energy_threshold": True,
        "pause_threshold": 0.75,
    },
    "rag": {
        "enabled": True,
        "max_files_per_request": 5,
        "max_bytes_per_file": 1_000_000,
        "max_total_attachment_bytes": 3_000_000,
        "max_indexed_chunks": 400,
        "max_retrieved_chunks": 6,
        "max_context_chars": 6_000,
        "chunk_target_chars": 800,
        "chunk_overlap_chars": 100,
        "safe_roots": ["."],
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
        ]
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
        "embedding_model": "BAAI/bge-m3",
        "fallback_embedding_model": "BAAI/bge-base-en-v1.5",
        "reranker_model": "BAAI/bge-reranker-base",
        "device": "auto",
        "batch_size": 8,
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
        "tts_voice": "af_heart",
        "follow_up_mode": True,
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


SETTINGS = load_settings()

LLAMA_CPP_URL = SETTINGS["services"]["llama_cpp_url"]
OLLAMA_URL = SETTINGS["services"]["ollama_url"]
OLLAMA_MODEL = SETTINGS["services"]["ollama_model"]
API_MODEL = SETTINGS["services"]["api_model"]
LOCAL = SETTINGS["services"].get("local", True)

SEARXNG_URL = SETTINGS["services"]["searxng_url"]
PROMPT_TEMPLATE = "<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"

RAG_SETTINGS = SETTINGS["rag"]
RAG_SERVICE_SETTINGS = SETTINGS["rag_service"]

WAKE_WORD_SETTINGS = SETTINGS["wake_word"]
SPEECH_SETTINGS = SETTINGS["speech"]
ASSISTANT_SETTINGS = SETTINGS["assistant"]
ASSISTANT_PERSONA = str(ASSISTANT_SETTINGS.get("persona", DEFAULT_SETTINGS["assistant"]["persona"])).strip()
MEMORY_FILE = BASE_DIR / "memory.json"
COMMAND_HISTORY_FILE = BASE_DIR / "command_history.json"
BROWSER_SETTINGS = SETTINGS.get("browser", DEFAULT_SETTINGS["browser"])

