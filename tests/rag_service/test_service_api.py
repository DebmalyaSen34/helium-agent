import tempfile
import unittest
from pathlib import Path

from rag_service.config import RagServiceConfig
from rag_service.doctor import run_doctor
from rag_service.service import RagEvidenceService


def config_for(root: Path) -> RagServiceConfig:
    return RagServiceConfig.from_settings({"rag_service": {"safe_roots": [str(root)], "cache_dir": str(root / ".cache")}})


class RagServiceApiTests(unittest.TestCase):
    def test_service_builds_evidence_for_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("# Risk\nThe risk is cache corruption.", encoding="utf-8")
            service = RagEvidenceService(config_for(root))

            pack = service.build_evidence_for_path(target, "what is the risk?")

            self.assertIn("cache corruption", pack.prompt)

    def test_api_endpoint_returns_evidence(self):
        try:
            from fastapi.testclient import TestClient
            from rag_service import api
        except ImportError:
            self.skipTest("fastapi is not installed in this interpreter")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("# Risk\nThe risk is slow startup.", encoding="utf-8")
            api._service = RagEvidenceService(config_for(root))
            client = TestClient(api.app)

            response = client.post("/v1/evidence/path", json={"file_path": str(target), "question": "what is the risk?"})

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["ok"])
            self.assertIn("slow startup", response.json()["evidence"]["prompt"])

    def test_doctor_returns_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            checks = run_doctor(config_for(Path(temp)))

            self.assertTrue(any(check.name == "cache_dir" and check.ok for check in checks))
