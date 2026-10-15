import re
from unittest.mock import patch

from rich.console import Console

from utils.code_render import (
    CodeMarkdown,
    DiffView,
    diff_rows,
    git_diff_view,
    highlight,
    looks_like_git_diff,
    parse_git_diff,
    parse_unified_diff,
)
from utils.file_change_display import (
    MAX_DIFF_LINES,
    display_file_change,
    display_file_status,
    display_patch,
)


def render(renderable, width: int = 80) -> str:
    console = Console(width=width, force_terminal=True, color_system="truecolor")
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def plain(renderable, width: int = 80) -> str:
    console = Console(width=width, color_system=None)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


OLD = 'def greet(name):\n    """Say hi."""\n    print("Hello", name)\n    return name\n'
NEW = 'def greet(name: str):\n    """Say hi."""\n    print("Hello", name)\n    return name\n'


# ── diff_rows ─────────────────────────────────────────────────────

def test_diff_rows_numbers_each_side():
    rows = diff_rows("a\nb\nc\n", "a\nB\nc\n")
    kinds = [(row.kind, row.text, row.old_no, row.new_no) for row in rows]
    assert ("-", "b", 2, None) in kinds
    assert ("+", "B", None, 2) in kinds
    assert (" ", "a", 1, 1) in kinds


def test_diff_rows_no_change():
    assert diff_rows("same\n", "same\n") == []


def test_diff_rows_marks_gap_between_distant_hunks():
    old = "".join(f"line{i}\n" for i in range(40))
    new = old.replace("line2\n", "two\n").replace("line35\n", "thirty-five\n")
    rows = diff_rows(old, new)
    assert sum(row.kind == "…" for row in rows) == 1


# ── parsing unified diffs ─────────────────────────────────────────

def test_parse_unified_diff_tracks_line_numbers():
    rows = parse_unified_diff("--- a/f\n+++ b/f\n@@ -10,3 +10,3 @@ def f():\n ctx\n-old\n+new\n ctx2\n")
    assert rows[0].kind == "…" and rows[0].text == "def f():"
    assert [(r.kind, r.old_no, r.new_no) for r in rows[1:]] == [(" ", 10, 10), ("-", 11, None), ("+", None, 11), (" ", 12, 12)]


def test_parse_git_diff_splits_files_and_statuses():
    text = (
        "diff --git a/one.py b/one.py\nindex 1..2 100644\n--- a/one.py\n+++ b/one.py\n@@ -1 +1 @@\n-a\n+b\n"
        "diff --git a/two.py b/two.py\nnew file mode 100644\n--- /dev/null\n+++ b/two.py\n@@ -0,0 +1,2 @@\n+x\n+y\n"
    )
    files = parse_git_diff(text)
    assert [(f.path, f.status, f.added, f.removed) for f in files] == [("one.py", "modified", 1, 1), ("two.py", "added", 2, 0)]
    assert looks_like_git_diff(text)
    assert not looks_like_git_diff("exit_code: 0\nhello")
    assert "one.py" in plain(git_diff_view(text)) and "two.py (new)" in plain(git_diff_view(text))


# ── rendering ─────────────────────────────────────────────────────

def test_highlight_returns_one_line_per_source_line():
    lines = highlight("x = 1\ny = 2\n", "python")
    assert [line.plain for line in lines] == ["x = 1", "y = 2"]
    assert lines[0].spans


def test_diff_view_keeps_indented_context_lines():
    out = plain(DiffView(diff_rows(OLD, NEW), "greet.py"))
    assert '"""Say hi."""' in out
    assert 'print("Hello", name)' in out
    assert "return name" in out


def test_diff_view_keeps_syntax_colours_on_changed_lines():
    out = render(DiffView(diff_rows(OLD, NEW), "greet.py"))
    added = next(line for line in out.splitlines() if "name: str" in re.sub(r"\x1b\[[0-9;]*m", "", line))
    # Several foreground colours on the added line means syntax highlighting survived.
    assert len(set(re.findall(r"38;2;(\d+;\d+;\d+)", added))) > 2


def test_diff_view_highlights_changed_words():
    out = render(DiffView(diff_rows("total = a + b\n", "total = a * b\n"), "x.py"))
    from utils.theme import current_theme

    word_bg = current_theme().diff_add_word_bg
    r, g, b = (int(word_bg[i:i + 2], 16) for i in (1, 3, 5))
    assert f"48;2;{r};{g};{b}" in out


def test_diff_view_truncates():
    rows = diff_rows("", "".join(f"l{i}\n" for i in range(100)))
    out = plain(DiffView(rows, "x.txt", max_rows=10))
    assert "90 more lines" in out


def test_code_markdown_renders_diff_fence_as_diff():
    out = plain(CodeMarkdown("```diff\n-old line\n+new line\n```"))
    assert "- old line" in out and "+ new line" in out


def test_code_markdown_labels_language():
    out = plain(CodeMarkdown("```python\nx = 1\n```"))
    assert "python" in out and "x = 1" in out


# ── display_file_change (integration) ─────────────────────────────

@patch("utils.file_change_display.console")
def test_display_new_file(mock_console):
    display_file_change("write_file", "test.py", None, "print('hi')\n")
    mock_console.print.assert_called_once()
    title = mock_console.print.call_args[0][0].title.plain
    assert "Created test.py" in title and "+1" in title


@patch("utils.file_change_display.console")
def test_display_delete_file(mock_console):
    display_file_change("delete_file", "old.py", "content\n", None)
    title = mock_console.print.call_args[0][0].title.plain
    assert "Deleted old.py" in title and "−1" in title


@patch("utils.file_change_display.console")
def test_display_edit_file(mock_console):
    display_file_change("replace_text", "greet.py", "hello\nworld\n", "hello\nuniverse\n")
    panel = mock_console.print.call_args[0][0]
    assert "Edited greet.py" in panel.title.plain
    assert "universe" in plain(panel)


@patch("utils.file_change_display.console")
def test_display_no_change_skips(mock_console):
    display_file_change("write_file", "test.py", "same\n", "same\n")
    mock_console.print.assert_not_called()


@patch("utils.file_change_display.console")
def test_display_long_change_is_capped(mock_console):
    display_file_change("create_file", "big.py", None, "x = 1\n" * (MAX_DIFF_LINES + 20))
    assert "20 more lines" in plain(mock_console.print.call_args[0][0])


@patch("utils.file_change_display.console")
def test_display_patch(mock_console):
    display_patch("file.py", "--- a/file\n+++ b/file\n@@ -1,1 +1,1 @@\n-old\n+new\n")
    panel = mock_console.print.call_args[0][0]
    assert "Patched file.py" in panel.title.plain
    assert "old" in plain(panel) and "new" in plain(panel)


@patch("utils.file_change_display.console")
def test_display_file_status_basic(mock_console):
    display_file_status("mkdir", "src/utils")
    rendered = str(mock_console.print.call_args[0][0])
    assert "Created folder" in rendered and "src/utils" in rendered


@patch("utils.file_change_display.console")
def test_display_file_status_with_detail(mock_console):
    display_file_status("copy_file", "a.py", "→ b.py")
    rendered = str(mock_console.print.call_args[0][0])
    assert "Copied" in rendered and "→ b.py" in rendered


# ── live reply shows git diffs ────────────────────────────────────

def test_live_reply_prints_git_diff_results():
    from utils.stream_render import LiveReply

    console = Console(width=80, color_system=None)
    reply = LiveReply(console, stream_text=False)
    diff = "exit_code: 0\ndiff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    with console.capture() as capture:
        reply.handle_event("tool_end", {"name": "execute_bash", "result": diff})
        reply.handle_event("tool_end", {"name": "read_file", "result": diff})
        reply.finish()
    out = capture.get()
    assert out.count("a.py") == 1 and "x = 2" in out
