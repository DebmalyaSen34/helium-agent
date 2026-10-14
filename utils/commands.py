"""Built-in slash commands: one table feeds dispatch, /help, and completion."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    name: str
    usage: str
    description: str


BUILTIN_COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand("/help", "/help", "Show this help guide."),
    SlashCommand("/code", "/code <task>", "Agentic coding: explore, plan, edit, verify, and report changes."),
    SlashCommand("/deep-research", "/deep-research <task>", "Run the deep research pipeline with multi-source evidence."),
    SlashCommand("/init", "/init", "Inspect the project and write a HELIUM.md with project instructions."),
    SlashCommand("/undo", "/undo", "Revert the last file change Helium made (shell command changes are not covered)."),
    SlashCommand("/model", "/model [name] [--save]", "Show the current model, or switch models for this session (--save persists it)."),
    SlashCommand("/usage", "/usage", "Show token and tool usage for this session."),
    SlashCommand("/clear", "/clear", "Clear the conversation history (memories and files are kept)."),
    SlashCommand("/skills", "/skills [list|create|remove|help]", "List, create, or remove skills."),
    SlashCommand("/notes", "/notes [text]", "Open your notes for this folder, or append a quick timestamped note."),
    SlashCommand("/exit", "/exit", "End the session."),
)

BUILTIN_SLASH_COMMANDS: tuple[str, ...] = tuple(command.name for command in BUILTIN_COMMANDS)


def parse_command(user_text: str, name: str) -> str | None:
    """Return the argument text when `user_text` invokes `name`, else None."""
    stripped = user_text.strip()
    if stripped == name:
        return ""
    if stripped.startswith(name + " "):
        return stripped[len(name) + 1:].strip()
    return None


EXIT_COMMANDS: frozenset[str] = frozenset({"/exit", "quit", "exit", "stop"})


__all__ = ["EXIT_COMMANDS", "BUILTIN_COMMANDS", "BUILTIN_SLASH_COMMANDS", "SlashCommand", "parse_command"]
