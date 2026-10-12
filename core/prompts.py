"""Single place that assembles system prompts for every agent mode.

The tool-calling protocol itself is not added here: the agent loop appends
the text `<action>` protocol only when it has to fall back to it, and native
tool calling sends tool schemas in the request instead.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from config.settings import ASSISTANT_PERSONA
from tools.registry import TOOL_POLICY

PromptMode = Literal["chat", "code", "skill", "subagent"]


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
    mode: PromptMode = "chat",
    *,
    user_prompt: str = "",
    skills: list[Any] | None = None,
    skill: Any | None = None,
    extra: str | None = None,
    persona: str | None = None,
) -> str:
    """Assemble the system prompt for `mode`.

    Every mode gets the persona, tool policy, date, and HELIUM.md project instructions.
    - chat: plus contextual skills, relevant memories, previous-session summary
    - code: plus `extra` (the coding workflow rules) and the previous-session summary
    - skill: plus the skill body
    - subagent: `persona` is the subagent role
    """
    sections: list[str | None] = [
        (persona if persona is not None else ASSISTANT_PERSONA),
        TOOL_POLICY,
        _date_line(),
    ]

    sections.append(_project_section())

    if mode == "chat":
        sections.append(_skills_section(skills))
        sections.append(_memories_section(user_prompt))
        sections.append(_previous_session_section())
    elif mode == "code":
        sections.append(extra)
        sections.append(_previous_session_section())
    elif mode == "skill" and skill is not None:
        sections.append(_skill_body_section(skill))

    if mode != "code" and extra:
        sections.append(extra)

    return "\n\n".join(section.strip() for section in sections if section)


__all__ = ["PromptMode", "build_system_prompt"]
