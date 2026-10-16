"""Single place that assembles system prompts for every agent mode.

The tool-calling protocol itself is not added here: the agent loop appends
the text `<action>` protocol only when it has to fall back to it, and native
tool calling sends tool schemas in the request instead.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from config.settings import ASSISTANT_PERSONA
from tools.registry import tool_policy

PromptMode = Literal["main", "skill", "subagent"]

# Helium is a coding agent first: these rules ride along with every main-mode turn.
CODING_GUIDELINES = """<coding_guidelines>
You are working in the user's project. Most requests are software engineering tasks: fixing bugs,
adding features, refactoring, explaining code, or running commands. Answer simple questions directly;
for anything that touches the code, work in a loop until the task is done:

1. Explore: locate code with glob_files and search_text, then read_file the parts you need.
   Batch independent reads in one turn when you can.
2. Plan: for multi-step changes, write a short plan (3-6 bullets) and keep it updated as you learn.
3. Edit: make targeted edits with edit_file; use write_file only for new files or complete rewrites.
   Keep diffs minimal and do not reformat unrelated code.
4. Verify: after changing code, tests, or configuration, run the smallest useful check
   (run_tests with a focused command, or execute_bash). Read failures carefully and fix the cause.
5. Report: when you changed files, end with a brief summary of what changed, how you verified it,
   and anything left undone. Keep it short; the user saw the edits as they happened.

Rules:
- read a file before editing it, and never invent file contents, APIs, or command output
- follow the conventions of the surrounding code: naming, comment density, idioms
- never claim tests passed unless a verification command actually ran and succeeded; if verification cannot run, say why
- if two attempts to fix the same failure don't work, stop and report what you found instead of looping
- if you are unsure about a library API or language feature, check with search_web or browse_url instead of guessing,
  but don't get stuck researching: start implementing once you know enough
- do only what was asked; mention other problems you notice instead of fixing them unasked
</coding_guidelines>"""


def _date_line() -> str:
    return f"Today's Date: {datetime.now().strftime('%B %d, %Y')}"


def _skills_section(skills: list[Any] | None) -> str | None:
    if not skills:
        return None
    contextual = [s for s in skills if not s.is_slash_command]
    if not contextual:
        return None
    lines = []
    for skill in contextual:
        hint = f" (trigger: {skill.trigger})" if skill.trigger else ""
        lines.append(f"- {skill.name}{hint}: {skill.description}")
    return "=== AVAILABLE SKILLS ===\n" + "\n".join(lines) + "\n========================"


def _memories_section(user_prompt: str) -> str | None:
    from tools.memory_ops import get_relevant_memories

    memories = get_relevant_memories(user_prompt) if user_prompt else []
    if not memories:
        return None
    memories_text = "\n".join(f"- {m}" for m in memories)
    return f"=== RELEVANT MEMORIES ===\n{memories_text}\n========================"


def _project_section() -> str | None:
    from core.project_context import project_instructions_section

    return project_instructions_section()


def _snapshot_section() -> str | None:
    from core.project_context import project_snapshot_section

    return project_snapshot_section()


def _previous_session_section() -> str | None:
    from tools.memory_ops import get_session_summary

    summary = get_session_summary()
    if not summary:
        return None
    return (
        "=== PREVIOUS SESSION (most recent turns in this project) ===\n"
        f"{summary}\n"
        "========================"
    )


def _skill_body_section(skill: Any) -> str:
    section = f'<skill name="{skill.name}">\n{skill.body}\n</skill>'
    if skill.argument_hint:
        section += f"\nArgument hint: {skill.argument_hint}"
    if skill.allowed_tools:
        section += f"\nOnly these tools are available for this skill: {', '.join(skill.allowed_tools)}"
    return section


def build_system_prompt(
    mode: PromptMode = "main",
    *,
    user_prompt: str = "",
    skills: list[Any] | None = None,
    skill: Any | None = None,
    extra: str | None = None,
    persona: str | None = None,
) -> str:
    """Assemble the system prompt for `mode`.

    Every mode gets the persona, tool policy, date, and HELIUM.md project instructions.
    - main: plus the coding guidelines, project snapshot, contextual skills,
      relevant memories, and previous-session summary
    - skill: plus the skill body
    - subagent: `persona` is the subagent role
    `extra` is appended last in any mode.
    """
    sections: list[str | None] = [
        (persona if persona is not None else ASSISTANT_PERSONA),
        tool_policy(subagents=mode == "main"),
        _date_line(),
    ]

    if mode == "main":
        sections.append(CODING_GUIDELINES)
        sections.append(_snapshot_section())

    sections.append(_project_section())

    if mode == "main":
        sections.append(_skills_section(skills))
        sections.append(_previous_session_section())
        # Last, because it changes with every prompt; everything above stays cacheable.
        sections.append(_memories_section(user_prompt))
    elif mode == "skill" and skill is not None:
        sections.append(_skill_body_section(skill))

    sections.append(extra)

    return "\n\n".join(section.strip() for section in sections if section)


__all__ = ["CODING_GUIDELINES", "PromptMode", "build_system_prompt"]
