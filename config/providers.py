"""Known OpenAI-compatible providers and chat-completions URL handling."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class Provider:
    name: str
    api_url: str
    default_model: str
    key_env: str | None = None
    note: str = ""


PROVIDERS: dict[str, Provider] = {
    "deepseek": Provider(
        name="deepseek",
        api_url="https://api.deepseek.com/chat/completions",
        default_model="deepseek-flash",
        key_env="DEEPSEEK_API_KEY",
        note="Models: deepseek-flash (fast, cheaper) and deepseek-v4-pro. Thinking mode is on by default.",
    ),
    "openrouter": Provider(
        name="openrouter",
        api_url="https://openrouter.ai/api/v1/chat/completions",
        default_model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        key_env="OPENROUTER_API_KEY",
    ),
    "ollama": Provider(
        name="ollama",
        api_url="http://localhost:11434/v1/chat/completions",
        default_model="",
        note="Any non-empty API key works for a local Ollama server.",
    ),
}


def normalize_chat_url(url: str | None) -> str | None:
    """Turn a provider base URL into its chat-completions endpoint.

    `https://api.deepseek.com` and `.../v1` get `/chat/completions` appended, and
    Ollama's native `/api/chat` is mapped to its OpenAI-compatible endpoint,
    since Helium only speaks the OpenAI chat-completions format.
    """
    if not url:
        return url
    url = url.strip()
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return url
    path = parts.path.rstrip("/")
    if path.endswith("/chat/completions"):
        return url
    if path == "/api/chat":
        path = "/v1/chat/completions"
    elif path in ("", "/v1", "/beta") or path.endswith("/v1"):
        path = f"{path}/chat/completions"
    else:
        return url
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def provider_for_url(url: str | None) -> Provider | None:
    if not url:
        return None
    host = urlsplit(url.strip()).netloc.lower()
    for provider in PROVIDERS.values():
        if urlsplit(provider.api_url).netloc.lower() == host:
            return provider
    return None


__all__ = ["PROVIDERS", "Provider", "normalize_chat_url", "provider_for_url"]
