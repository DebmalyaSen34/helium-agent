import os

DEFAULTS = {
    "base_url": "https://api.example.com",
    "timeout_seconds": 30,
    "retries": 2,
}


def load_config(environ=None) -> dict:
    """Defaults, overridden by APP_<KEY> environment variables."""
    environ = os.environ if environ is None else environ
    config = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        raw = environ.get(f"APP_{key.upper()}")
        if raw is not None:
            config[key] = type(default)(raw)
    return config
