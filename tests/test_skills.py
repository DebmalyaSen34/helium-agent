import unittest
import tempfile
from pathlib import Path

from skills.loader import Skill, parse_skill_file, discover_skills, match_skill_trigger
from skills.manager import create_skill, remove_skill


SAMPLE_SKILL = """\
---
name: test-skill
description: "A test skill for unit testing"
trigger: /test-skill
version: "1.0"
argument-hint: "<arg1> [arg2]"
allowed-tools: ["read_file", "execute_bash"]
model: "mimo-v2.5-pro"
---

# Test Skill

This is the body of the test skill.
It contains instructions for the LLM.
"""

MINIMAL_SKILL = """\
---
name: minimal
description: "Minimal skill with only required fields"
---

Just a body.
"""

CONTEXTUAL_SKILL = """\
---
name: code-review
description: "Use when reviewing code for bugs and improvements"
---

Review instructions here.
"""

INVALID_NO_FRONTMATTER = """\
This is just a regular markdown file with no frontmatter.
"""

INVALID_BAD_YAML = """\
---
name: [broken
description: yaml
---

Body here.
"""

INVALID_NO_NAME = """\
---
description: "Has no name field"
---

Body.
"""


class ParseSkillFileTests(unittest.TestCase):
    def _write_temp(self, content: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
        tmp.write(content)
        tmp.close()
        return Path(tmp.name)

    def test_parse_full_skill(self):
        path = self._write_temp(SAMPLE_SKILL)
        skill = parse_skill_file(path)
        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "test-skill")
        self.assertEqual(skill.description, "A test skill for unit testing")
        self.assertEqual(skill.trigger, "/test-skill")
        self.assertEqual(skill.version, "1.0")
        self.assertEqual(skill.argument_hint, "<arg1> [arg2]")
        self.assertEqual(skill.allowed_tools, ["read_file", "execute_bash"])
        self.assertEqual(skill.model, "mimo-v2.5-pro")
        self.assertIn("This is the body", skill.body)
        self.assertTrue(skill.is_slash_command)

    def test_parse_minimal_skill(self):
        path = self._write_temp(MINIMAL_SKILL)
        skill = parse_skill_file(path)
        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "minimal")
        self.assertEqual(skill.description, "Minimal skill with only required fields")
        self.assertIsNone(skill.trigger)
        self.assertEqual(skill.allowed_tools, [])
        self.assertTrue(skill.is_slash_command is False)

    def test_parse_contextual_skill(self):
        path = self._write_temp(CONTEXTUAL_SKILL)
        skill = parse_skill_file(path)
        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "code-review")
        self.assertIsNone(skill.trigger)
        self.assertFalse(skill.is_slash_command)

    def test_parse_no_frontmatter_returns_none(self):
        path = self._write_temp(INVALID_NO_FRONTMATTER)
        self.assertIsNone(parse_skill_file(path))

    def test_parse_bad_yaml_returns_none(self):
        path = self._write_temp(INVALID_BAD_YAML)
        self.assertIsNone(parse_skill_file(path))

    def test_parse_no_name_returns_none(self):
        path = self._write_temp(INVALID_NO_NAME)
        self.assertIsNone(parse_skill_file(path))

    def test_parse_nonexistent_file_returns_none(self):
        self.assertIsNone(parse_skill_file(Path("/nonexistent/SKILL.md")))

    def test_trigger_normalized_with_slash(self):
        path = self._write_temp("---\nname: x\ndescription: d\ntrigger: noslash\n---\nbody")
        skill = parse_skill_file(path)
        self.assertEqual(skill.trigger, "/noslash")

    def test_allowed_tools_as_csv_string(self):
        path = self._write_temp("---\nname: x\ndescription: d\nallowed-tools: read_file, write_file\n---\nbody")
        skill = parse_skill_file(path)
        self.assertEqual(skill.allowed_tools, ["read_file", "write_file"])


class DiscoverSkillsTests(unittest.TestCase):
    def test_discovers_from_user_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "skills" / "my-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL)

            # Patch _skill_dirs to use our temp dir
            import skills.loader as loader
            original = loader._skill_dirs
            loader._skill_dirs = lambda ws=None: [Path(tmpdir) / "skills"]
            try:
                skills = discover_skills()
                self.assertEqual(len(skills), 1)
                self.assertEqual(skills[0].name, "test-skill")
            finally:
                loader._skill_dirs = original

    def test_deduplicates_by_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Both dirs have skills with the same name field
            d1 = Path(tmpdir) / "dir1" / "my-skill"
            d1.mkdir(parents=True)
            (d1 / "SKILL.md").write_text(SAMPLE_SKILL)
            # Second dir: same skill name, different description
            dup = "---\nname: test-skill\ndescription: duplicate\n---\nDup body."
            d2 = Path(tmpdir) / "dir2" / "my-skill"
            d2.mkdir(parents=True)
            (d2 / "SKILL.md").write_text(dup)

            import skills.loader as loader
            original = loader._skill_dirs
            loader._skill_dirs = lambda ws=None: [Path(tmpdir) / "dir1", Path(tmpdir) / "dir2"]
            try:
                skills = discover_skills()
                self.assertEqual(len(skills), 1)
                self.assertEqual(skills[0].name, "test-skill")  # first dir wins
            finally:
                loader._skill_dirs = original

    def test_skips_invalid_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "skills" / "bad-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(INVALID_NO_FRONTMATTER)

            import skills.loader as loader
            original = loader._skill_dirs
            loader._skill_dirs = lambda ws=None: [Path(tmpdir) / "skills"]
            try:
                skills = discover_skills()
                self.assertEqual(len(skills), 0)
            finally:
                loader._skill_dirs = original


class MatchSkillTriggerTests(unittest.TestCase):
    def _skill(self, trigger=None):
        return Skill(name="test", description="d", trigger=trigger)

    def test_exact_match(self):
        skill = self._skill("/myskill")
        result = match_skill_trigger("/myskill", [skill])
        self.assertIsNotNone(result)
        matched, args = result
        self.assertEqual(matched.name, "test")
        self.assertEqual(args, "")

    def test_match_with_args(self):
        skill = self._skill("/myskill")
        result = match_skill_trigger("/myskill hello world", [skill])
        self.assertIsNotNone(result)
        _, args = result
        self.assertEqual(args, "hello world")

    def test_no_match(self):
        skill = self._skill("/myskill")
        result = match_skill_trigger("/other", [skill])
        self.assertIsNone(result)

    def test_no_match_partial_prefix(self):
        skill = self._skill("/myskill")
        result = match_skill_trigger("/myskill2", [skill])
        self.assertIsNone(result)

    def test_contextual_skill_not_matched(self):
        skill = self._skill()  # no trigger
        result = match_skill_trigger("anything", [skill])
        self.assertIsNone(result)


class SkillManagerTests(unittest.TestCase):
    def test_create_skill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            import skills.loader as loader
            import skills.manager as mgr
            original = loader._skill_dirs
            loader._skill_dirs = lambda ws=None: [Path(tmpdir) / "skills"]
            try:
                path = create_skill("my-new-skill")
                self.assertTrue(path.exists())
                content = path.read_text()
                self.assertIn("name: my-new-skill", content)
                self.assertIn("trigger: /my-new-skill", content)

                # Verify it parses
                skill = parse_skill_file(path)
                self.assertIsNotNone(skill)
                self.assertEqual(skill.name, "my-new-skill")
            finally:
                loader._skill_dirs = original

    def test_remove_skill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            import skills.loader as loader
            original = loader._skill_dirs
            loader._skill_dirs = lambda ws=None: [Path(tmpdir) / "skills"]
            try:
                create_skill("doomed")
                ok, msg = remove_skill("doomed")
                self.assertTrue(ok)
                self.assertIn("Removed", msg)
                # Verify gone
                self.assertFalse((Path(tmpdir) / "skills" / "doomed").exists())
            finally:
                loader._skill_dirs = original

    def test_remove_nonexistent_skill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            import skills.loader as loader
            original = loader._skill_dirs
            loader._skill_dirs = lambda ws=None: [Path(tmpdir) / "skills"]
            try:
                ok, msg = remove_skill("ghost")
                self.assertFalse(ok)
                self.assertIn("not found", msg)
            finally:
                loader._skill_dirs = original


class SkillSystemPromptTests(unittest.TestCase):
    def test_contextual_skills_injected_into_prompt(self):
        from core.llm import build_system_prompt

        skills = [
            Skill(name="code-review", description="Use when reviewing code"),
            Skill(name="slash-skill", description="Has trigger", trigger="/slash"),
        ]
        prompt = build_system_prompt("hello", skills=skills)
        self.assertIn("code-review", prompt)
        self.assertIn("Use when reviewing code", prompt)
        self.assertIn("AVAILABLE SKILLS", prompt)
        # Slash-command skill should NOT be in the AVAILABLE SKILLS section
        section = prompt.split("AVAILABLE SKILLS")[1].split("===")[0]
        self.assertNotIn("slash-skill", section)

    def test_no_skills_section_when_empty(self):
        from core.llm import build_system_prompt
        prompt = build_system_prompt("hello", skills=[])
        self.assertNotIn("AVAILABLE SKILLS", prompt)

    def test_no_skills_section_when_none(self):
        from core.llm import build_system_prompt
        prompt = build_system_prompt("hello", skills=None)
        self.assertNotIn("AVAILABLE SKILLS", prompt)

    def test_only_contextual_skills_in_prompt(self):
        from core.llm import build_system_prompt
        skills = [
            Skill(name="ctx", description="Contextual one"),
            Skill(name="slash", description="Slash one", trigger="/slash"),
        ]
        prompt = build_system_prompt("hello", skills=skills)
        self.assertIn("ctx", prompt)
        # slash should not appear in AVAILABLE SKILLS
        if "AVAILABLE SKILLS" in prompt:
            skills_section = prompt.split("AVAILABLE SKILLS")[1].split("===")[0]
            self.assertNotIn("slash", skills_section)


if __name__ == "__main__":
    unittest.main()
