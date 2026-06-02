import os
from prompt_toolkit.completion import Completer, Completion

SLASH_COMMANDS = (
    "/code",
    "/deep-research",
)

class WorkspaceFileCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        if text.startswith("/") and " " not in text:
            for command in SLASH_COMMANDS:
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
