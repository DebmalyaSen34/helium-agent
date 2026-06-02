from prompt_toolkit.document import Document
from utils.completer import WorkspaceFileCompleter

def test_workspace_file_completer():
    completer = WorkspaceFileCompleter()
    doc = Document("Hello @REA", cursor_position=10)
    
    completions = list(completer.get_completions(doc, None))
    # Verify it matches README.md in workspace
    matches = [c.text for c in completions]
    assert "README.md" in matches

def test_slash_command_completer_suggests_code_and_deep_research():
    completer = WorkspaceFileCompleter()
    doc = Document("/", cursor_position=1)

    completions = list(completer.get_completions(doc, None))
    matches = [c.text for c in completions]

    assert "/code" in matches
    assert "/deep-research" in matches

def test_slash_command_completer_filters_by_prefix():
    completer = WorkspaceFileCompleter()
    doc = Document("/d", cursor_position=2)

    completions = list(completer.get_completions(doc, None))
    matches = [c.text for c in completions]

    assert matches == ["/deep-research"]
