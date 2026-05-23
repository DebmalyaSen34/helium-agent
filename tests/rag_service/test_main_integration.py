import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rag_service.config import RagServiceConfig

try:
    import main
except ImportError as exc:
    main = None
    MAIN_IMPORT_ERROR = exc
else:
    MAIN_IMPORT_ERROR = None


@unittest.skipIf(main is None, f"main.py dependencies are not installed: {MAIN_IMPORT_ERROR}")
class MainRagIntegrationTests(unittest.TestCase):
    def test_prepare_rag_prompt_leaves_normal_chat_unchanged(self):
        self.assertEqual(main.prepare_rag_prompt("hello there"), "hello there")

    def test_prepare_rag_prompt_uses_evidence_for_attachment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("hello", encoding="utf-8")
            config = RagServiceConfig.from_settings(
                {
                    "rag_service": {
                        "safe_roots": [str(root)],
                        "cache_dir": str(root / ".cache"),
                        "service_url": "http://127.0.0.1:8765",
                    }
                }
            )

            with patch("main.load_rag_service_config", return_value=config), patch(
                "main.RagServiceClient"
            ) as client_class:
                client_class.return_value.evidence_for_path.return_value = {
                    "prompt": "Attached file evidence pack:\nhello",
                    "citations": ["[file:notes.md#chunk-0 lines 1-1]"],
                }

                prompt = main.prepare_rag_prompt(f"summarize @{target}")

            self.assertIn("Attached file evidence pack", prompt)
            client_class.return_value.evidence_for_path.assert_called_once()
