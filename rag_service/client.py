from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import requests

from rag_service.config import RagServiceConfig
from rag_service.models import RagError


class RagServiceClient:
    def __init__(self, config: RagServiceConfig) -> None:
        self.config = config

    def health(self) -> bool:
        try:
            response = requests.get(f"{self.config.service_url}/health", timeout=2)
            return response.ok and bool(response.json().get("ok"))
        except requests.RequestException:
            return False

    def ensure_available(self) -> None:
        if self.health():
            return
        if not self.config.auto_start:
            raise RagError("service_unavailable", "RAG service is not running.")

        subprocess.Popen(
            [sys.executable, "-m", "rag_service", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.health():
                return
            time.sleep(0.25)
        raise RagError("service_unavailable", "RAG service did not become ready after auto-start.")

    def evidence_for_path(self, file_path: Path, question: str, *, debug: bool = False) -> dict:
        self.ensure_available()
        try:
            response = requests.post(
                f"{self.config.service_url}/v1/evidence/path",
                json={"file_path": str(file_path), "question": question, "debug": debug},
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise RagError("service_unavailable", f"RAG service request failed: {exc}") from exc

        data = response.json()
        if not response.ok or not data.get("ok"):
            error = data.get("error", {})
            raise RagError(str(error.get("code", "rag_error")), str(error.get("message", "RAG service failed.")))
        return data["evidence"]
