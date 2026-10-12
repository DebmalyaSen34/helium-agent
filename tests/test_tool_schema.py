import json
import unittest
from typing import Literal

from tools.registry import AVAILABLE_TOOLS, build_openai_tools, execute_tool_call, render_text_protocol_prompt
from tools.schema import function_to_schema, validate_args


class FunctionToSchemaTests(unittest.TestCase):
    def test_read_file_schema_marks_optional_params(self):
        schema = AVAILABLE_TOOLS["read_file"].schema()
        self.assertEqual(schema["required"], ["path"])
        self.assertEqual(schema["properties"]["path"], {"type": "string"})
        self.assertEqual(schema["properties"]["start_line"]["type"], "integer")
        self.assertEqual(schema["properties"]["max_chars"]["default"], 20000)
        self.assertFalse(schema["additionalProperties"])

    def test_literal_and_union_types(self):
        def sample(kind: Literal["a", "b"], ident: str | int, tags: list[str] | None = None) -> str:
            return ""

        schema = function_to_schema(sample, {"kind": "which kind"})
        self.assertEqual(schema["properties"]["kind"], {"enum": ["a", "b"], "type": "string", "description": "which kind"})
        self.assertEqual(schema["properties"]["ident"], {"anyOf": [{"type": "string"}, {"type": "integer"}]})
        self.assertEqual(schema["properties"]["tags"], {"type": "array", "items": {"type": "string"}})
        self.assertEqual(schema["required"], ["kind", "ident"])

    def test_every_registered_tool_has_a_valid_json_schema(self):
        tools = build_openai_tools()
        self.assertEqual(len(tools), len(AVAILABLE_TOOLS))
        for tool in tools:
            json.dumps(tool)
            self.assertEqual(tool["type"], "function")
            self.assertEqual(tool["function"]["parameters"]["type"], "object")

    def test_subagent_wrappers_use_explicit_schema(self):
        schema = AVAILABLE_TOOLS["delegate_task"].schema()
        self.assertEqual(schema["required"], ["agent_id", "task"])

    def test_build_openai_tools_filters_by_name(self):
        names = [tool["function"]["name"] for tool in build_openai_tools(["read_file", "nope", "get_time"])]
        self.assertEqual(names, ["read_file", "get_time"])


class ArgumentValidationTests(unittest.TestCase):
    def test_unknown_argument_is_reported_with_accepted_names(self):
        result = execute_tool_call("read_file", {"file": "README.md"})
        self.assertIn("unknown argument(s) file", result)
        self.assertIn("path", result)

    def test_missing_required_argument_is_reported(self):
        problem = validate_args(AVAILABLE_TOOLS["read_file"].schema(), {})
        self.assertIn("missing required argument(s) path", problem)

    def test_text_protocol_prompt_lists_signatures(self):
        prompt = render_text_protocol_prompt(["read_file"])
        self.assertIn("read_file(path: str", prompt)
        self.assertIn("<action>", prompt)
        self.assertNotIn("search_web(", prompt)


if __name__ == "__main__":
    unittest.main()
