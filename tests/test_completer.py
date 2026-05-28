from prompt_toolkit.document import Document
from utils.completer import WorkspaceFileCompleter

def test_workspace_file_completer():
    completer = WorkspaceFileCompleter()
    doc = Document("Hello @REA", cursor_position=10)
    
    completions = list(completer.get_completions(doc, None))
    # Verify it matches README.md in workspace
    matches = [c.text for c in completions]
    assert "README.md" in matches
