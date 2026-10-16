import os

from prompt_toolkit.document import Document
from utils.completer import WorkspaceFileCompleter

def test_workspace_file_completer():
    completer = WorkspaceFileCompleter()
    doc = Document("Hello @REA", cursor_position=10)
    
    completions = list(completer.get_completions(doc, None))
    # Verify it matches README.md in workspace
    matches = [c.text for c in completions]
    assert "README.md" in matches

def test_slash_command_completer_suggests_builtin_commands():
    completer = WorkspaceFileCompleter()
    doc = Document("/", cursor_position=1)

    completions = list(completer.get_completions(doc, None))
    matches = [c.text for c in completions]

    assert "/code" not in matches
    assert "/deep-research" in matches
    assert "/help" in matches

def test_slash_command_completer_filters_help_by_prefix():
    completer = WorkspaceFileCompleter()
    doc = Document("/h", cursor_position=2)

    completions = list(completer.get_completions(doc, None))
    matches = [c.text for c in completions]

    assert matches == ["/help"]

def test_slash_command_completer_filters_by_prefix():
    completer = WorkspaceFileCompleter()
    doc = Document("/d", cursor_position=2)

    completions = list(completer.get_completions(doc, None))
    matches = [c.text for c in completions]

    assert matches == ["/deep-research"]

def test_slash_command_completer_includes_session_commands():
    completer = WorkspaceFileCompleter()
    matches = [c.text for c in completer.get_completions(Document("/", cursor_position=1), None)]
    for command in ("/clear", "/model", "/undo", "/usage", "/init"):
        assert command in matches


def _completer_in(tmp_path, monkeypatch, names):
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    monkeypatch.chdir(tmp_path)
    return WorkspaceFileCompleter()


def _file_completions(completer, text):
    return [c.text for c in completer.get_completions(Document(text, cursor_position=len(text)), None)]


def test_file_suggestions_are_capped(tmp_path, monkeypatch):
    from utils.completer import MAX_FILE_SUGGESTIONS

    completer = _completer_in(tmp_path, monkeypatch, [f"src/module_{i}.py" for i in range(MAX_FILE_SUGGESTIONS + 30)])

    assert len(_file_completions(completer, "@module")) == MAX_FILE_SUGGESTIONS


def test_file_suggestions_rank_name_matches_first(tmp_path, monkeypatch):
    completer = _completer_in(tmp_path, monkeypatch, ["docs/notes/app_guide.md", "src/app.py", "deep/nested/app.py"])

    assert _file_completions(completer, "@app") == ["src/app.py", "deep/nested/app.py", "docs/notes/app_guide.md"]


def test_no_file_suggestions_once_the_question_starts(tmp_path, monkeypatch):
    completer = _completer_in(tmp_path, monkeypatch, ["README.md"])

    assert _file_completions(completer, "@README.md what") == []


def test_file_list_is_reused_between_keystrokes(tmp_path, monkeypatch):
    completer = _completer_in(tmp_path, monkeypatch, ["src/app.py"])
    _file_completions(completer, "@a")

    walks = []
    real_walk = os.walk
    monkeypatch.setattr("utils.completer.os.walk", lambda *a, **k: walks.append(1) or real_walk(*a, **k))
    _file_completions(completer, "@ap")
    _file_completions(completer, "@app")

    assert walks == []
