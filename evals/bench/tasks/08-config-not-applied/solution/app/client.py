from app.config import load_config


class HttpClient:
    def __init__(self, config: dict | None = None):
        config = config or load_config()
        self.base_url = config["base_url"]
        self.timeout = config["timeout_seconds"]
        self.retries = config.get("retries", 0)

    def describe(self) -> str:
        return f"{self.base_url} (timeout={self.timeout}s, retries={self.retries})"
