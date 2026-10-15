import heapq
import os
import time
from typing import Any

from prompt_toolkit.completion import Completer, Completion

from utils.commands import BUILTIN_SLASH_COMMANDS

SKILLS_SUBCOMMANDS = (
    "list",
    "create",
    "remove",
    "help",
)

COMPLETION_IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "graphify-out",
    ".cache",
    ".gemini",
    ".claude",
    "dist",
    "build",
}
# A rescan walks the whole tree, so the list is kept for a while; a change in the
# top folder (a new file or directory there) still refreshes it at once.
FILE_CACHE_SECONDS = 30.0
MAX_INDEXED_FILES = 20_000
MAX_FILE_SUGGESTIONS = 50


class WorkspaceFileCompleter(Completer):
    def __init__(self, skills: list[Any] | None = None):
        self._skills = skills or []
        self._file_cache: list[str] = []
        self._file_cache_lower: list[str] = []
        self._file_cache_key: tuple[str, float] | None = None
        self._file_cache_time = 0.0

    def _slash_commands(self) -> list[str]:
        cmds = list(BUILTIN_SLASH_COMMANDS)
        for skill in self._skills:
            if skill.trigger and skill.trigger not in cmds:
                cmds.append(skill.trigger)
        return cmds

    def _workspace_files(self) -> list[str]:
        """Workspace files for @-completion, cached briefly so typing stays fast."""
        cwd = os.getcwd()
        try:
            mtime = os.stat(cwd).st_mtime
        except OSError:
            mtime = 0.0
        key = (cwd, mtime)
        now = time.monotonic()
        if key == self._file_cache_key and now - self._file_cache_time < FILE_CACHE_SECONDS:
            return self._file_cache

        files = []
        for root, dirs, filenames in os.walk("."):
            dirs[:] = [d for d in dirs if d not in COMPLETION_IGNORED_DIRS]
            for f in filenames:
                rel_path = os.path.relpath(os.path.join(root, f), ".")
                if rel_path.startswith("./"):
                    rel_path = rel_path[2:]
                if not rel_path.startswith("."):
                    files.append(rel_path)
            if len(files) >= MAX_INDEXED_FILES:
                del files[MAX_INDEXED_FILES:]
                break

        self._file_cache = files
        self._file_cache_lower = [f.lower() for f in files]
        self._file_cache_key = key
        self._file_cache_time = now
        return files

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # /skills subcommand completion
        if text.startswith("/skills ") and text.count(" ") == 1:
            partial = text.split(" ", 1)[1]
            for sub in SKILLS_SUBCOMMANDS:
                if sub.startswith(partial):
                    yield Completion(sub, start_position=-len(partial))
            return

        # /theme names (and /theme preview <name>)
        if text.startswith("/theme ") and (text.count(" ") == 1 or (text.startswith("/theme preview ") and text.count(" ") == 2)):
            from utils.theme import available_themes

            partial = text.rsplit(" ", 1)[1]
            extras = ["list", "preview", "create"] if text.count(" ") == 1 else []
            for name in [*available_themes(), *extras]:
                if name.startswith(partial):
                    yield Completion(name, start_position=-len(partial))
            return

        # Slash command completion (including skill triggers)
        if text.startswith("/") and " " not in text:
            for command in self._slash_commands():
                if command.startswith(text):
                    yield Completion(command, start_position=-len(text))
            return

        # Trigger autocomplete when typing after the '@' mention symbol
        if "@" in text:
            query = text.split("@")[-1]
            if any(ch.isspace() for ch in query):
                return  # the mention is finished; the user is typing the question
            for f in self._file_matches(query):
                yield Completion(f, start_position=-len(query))

    def _file_matches(self, query: str) -> list[str]:
        """The best few files containing `query`: name matches first, then shorter paths."""
        files = self._workspace_files()
        needle = query.lower()

        def rank(index: int) -> tuple[int, int, str]:
            path = self._file_cache_lower[index]
            name = os.path.basename(path)
            tier = 0 if name.startswith(needle) else 1 if path.startswith(needle) else 2 if needle in name else 3
            return tier, len(path), path

        matches = (i for i, path in enumerate(self._file_cache_lower) if needle in path)
        return [files[i] for i in heapq.nsmallest(MAX_FILE_SUGGESTIONS, matches, key=rank)]
