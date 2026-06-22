import os
from typing import Any
from prompt_toolkit.completion import Completer, Completion

BUILTIN_SLASH_COMMANDS = (
    "/help",
    "/code",
    "/deep-research",
    "/skills",
)

SKILLS_SUBCOMMANDS = (
    "list",
    "create",
    "remove",
    "help",
)


class WorkspaceFileCompleter(Completer):
    def __init__(self, skills: list[Any] | None = None):
        self._skills = skills or []

    def _slash_commands(self) -> list[str]:
        cmds = list(BUILTIN_SLASH_COMMANDS)
        for skill in self._skills:
            if skill.trigger and skill.trigger not in cmds:
                cmds.append(skill.trigger)
        return cmds

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # /skills subcommand completion
        if text.startswith("/skills ") and text.count(" ") == 1:
            partial = text.split(" ", 1)[1]
            for sub in SKILLS_SUBCOMMANDS:
                if sub.startswith(partial):
                    yield Completion(sub, start_position=-len(partial))
            return

        # Slash command completion (including skill triggers)
        if text.startswith("/") and " " not in text:
            for command in self._slash_commands():
                if command.startswith(text):
                    yield Completion(command, start_position=-len(text))
            return

        # Trigger autocomplete when typing after the '@' mention symbol
        if "@" in text:
            parts = text.split("@")
            query = parts[-1]

            # Scan files in the current workspace, ignoring virtual environments and logs
            files = []
            for root, dirs, filenames in os.walk("."):
                # Prune directories in place to optimize performance
                dirs[:] = [
                    d for d in dirs
                    if d not in {".git", ".venv", "__pycache__", "node_modules", "graphify-out", ".cache", ".gemini", ".claude"}
                ]
                for f in filenames:
                    rel_path = os.path.relpath(os.path.join(root, f), ".")
                    if rel_path.startswith("./"):
                        rel_path = rel_path[2:]
                    if not rel_path.startswith("."):
                        files.append(rel_path)

            # Filter files using fuzzy keyword matching
            for f in files:
                if query.lower() in f.lower():
                    yield Completion(f, start_position=-len(query))
