import unittest

import tools.web_search
from tools.registry import TOOL_PROMPT
from tools.search.pipeline import search_web as pipeline_search_web


class SearchCompatibilityTests(unittest.TestCase):
    def test_legacy_search_web_entrypoint_delegates_to_pipeline(self):
        self.assertIs(tools.web_search.search_web, pipeline_search_web)

    def test_tool_prompt_describes_structured_evidence(self):
        self.assertIn("structured evidence", TOOL_PROMPT)
        self.assertIn("confidence", TOOL_PROMPT.casefold())
        self.assertIn("sources", TOOL_PROMPT.casefold())

    def test_file_tool_prompt_document_delete(self):
        self.assertIn("delete_file", TOOL_PROMPT)
        self.assertIn("permanently deletes", TOOL_PROMPT)
        self.assertIn("project root", TOOL_PROMPT)

if __name__ == "__main__":
    unittest.main()
