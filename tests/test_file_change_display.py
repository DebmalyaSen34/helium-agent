import pytest
from unittest.mock import patch
from rich.text import Text

from utils.file_change_display import (
    _diff_lines,
    _style_lines,
    _addition_body,
    _deletion_body,
    _build_diff_body,
    _truncate,
    display_file_change,
    display_patch,
    display_file_status,
    MAX_DIFF_LINES,
)


# ── _diff_lines ───────────────────────────────────────────────────

def test_diff_lines_basic():
    old = "line1\nline2\nline3\n"
    new = "line1\nmodified\nline3\n"
    lines = _diff_lines(old, new)
    text = "".join(lines)
    assert "-line2" in text
    assert "+modified" in text


def test_diff_lines_no_change():
    old = "same\n"
    new = "same\n"
    lines = _diff_lines(old, new)
    assert lines == []


def test_diff_lines_new_file():
    old = ""
    new = "hello\nworld\n"
    lines = _diff_lines(old, new)
    text = "".join(lines)
    assert "+hello" in text
    assert "+world" in text


def test_diff_lines_empty_old():
    old = ""
    new = "content\n"
    lines = _diff_lines(old, new)
    text = "".join(lines)
    assert "+content" in text


def test_diff_lines_empty_new():
    old = "content\n"
    new = ""
    lines = _diff_lines(old, new)
    text = "".join(lines)
    assert "-content" in text


# ── _style_lines ──────────────────────────────────────────────────

def test_style_lines_returns_text_per_line():
    lines = _style_lines("print('hi')\nprint('bye')\n", "test.py")
    assert len(lines) == 2
    assert all(isinstance(line, Text) for line in lines)
    assert lines[0].plain == "print('hi')"
    assert lines[1].plain == "print('bye')"


def test_style_lines_no_trailing_newline():
    lines = _style_lines("one\ntwo", "test.py")
    assert len(lines) == 2
    assert lines[-1].plain == "two"


def test_style_lines_empty():
    lines = _style_lines("", "test.py")
    assert lines == []


def test_style_lines_has_syntax_spans():
    lines = _style_lines("def foo(): pass\n", "test.py")
    # should have at least one styled span for the keyword 'def'
    assert len(lines[0]._spans) > 0


# ── _addition_body / _deletion_body ───────────────────────────────

def test_addition_body_prefixes_with_plus():
    styled = _style_lines("x = 1\n", "test.py")
    body = _addition_body(styled)
    assert body.plain.startswith("+")
    assert "x = 1" in body.plain


def test_addition_body_has_green():
    styled = _style_lines("x = 1\n", "test.py")
    body = _addition_body(styled)
    styles = str(body._spans)
    assert "green" in styles


def test_deletion_body_prefixes_with_minus():
    styled = _style_lines("x = 1\n", "test.py")
    body = _deletion_body(styled)
    assert body.plain.startswith("-")
    assert "x = 1" in body.plain


def test_deletion_body_has_red():
    styled = _style_lines("x = 1\n", "test.py")
    body = _deletion_body(styled)
    styles = str(body._spans)
    assert "red" in styles


# ── _build_diff_body ──────────────────────────────────────────────

def test_build_diff_body_contains_markers():
    old = "a\nb\nc\n"
    new = "a\nB\nc\n"
    raw = _diff_lines(old, new)
    old_s = _style_lines(old, "test.py")
    new_s = _style_lines(new, "test.py")
    body = _build_diff_body(raw, old_s, new_s)
    assert "-b" in body.plain
    assert "+B" in body.plain


def test_build_diff_body_has_hunk_header():
    old = "a\n"
    new = "b\n"
    raw = _diff_lines(old, new)
    old_s = _style_lines(old, "test.py")
    new_s = _style_lines(new, "test.py")
    body = _build_diff_body(raw, old_s, new_s)
    assert "@@" in body.plain


# ── _truncate ─────────────────────────────────────────────────────

def test_truncate_short_text_unchanged():
    text = Text("line\n" * 10)
    result = _truncate(text, max_lines=50)
    assert result.plain == text.plain


def test_truncate_long_text_is_capped():
    text = Text("line\n" * 100)
    result = _truncate(text, max_lines=10)
    result_lines = result.plain.count("\n")
    assert result_lines <= 12  # 10 content + truncation notice + trailing


def test_truncate_adds_notice():
    text = Text("line\n" * 100)
    result = _truncate(text, max_lines=10)
    assert "truncated" in result.plain


# ── display_file_change (integration) ─────────────────────────────

@patch("utils.file_change_display.console")
def test_display_new_file(mock_console):
    display_file_change("write_file", "test.py", None, "print('hi')\n")
    mock_console.print.assert_called_once()
    panel = mock_console.print.call_args[0][0]
    assert "write_file" in panel.title
    assert "test.py" in panel.title


@patch("utils.file_change_display.console")
def test_display_delete_file(mock_console):
    display_file_change("delete_file", "old.py", "content\n", None)
    mock_console.print.assert_called_once()
    panel = mock_console.print.call_args[0][0]
    assert "delete_file" in panel.title


@patch("utils.file_change_display.console")
def test_display_edit_file(mock_console):
    old = "hello\nworld\n"
    new = "hello\nuniverse\n"
    display_file_change("replace_text", "greet.py", old, new)
    mock_console.print.assert_called_once()
    panel = mock_console.print.call_args[0][0]
    assert "replace_text" in panel.title


@patch("utils.file_change_display.console")
def test_display_no_change_skips(mock_console):
    content = "same\n"
    display_file_change("write_file", "test.py", content, content)
    mock_console.print.assert_not_called()


@patch("utils.file_change_display.console")
def test_display_create_file(mock_console):
    display_file_change("create_file", "new.py", None, "x = 1\n")
    mock_console.print.assert_called_once()


# ── display_patch ─────────────────────────────────────────────────

@patch("utils.file_change_display.console")
def test_display_patch(mock_console):
    patch_text = "--- a/file\n+++ b/file\n@@ -1,1 +1,1 @@\n-old\n+new\n"
    display_patch("file.py", patch_text)
    mock_console.print.assert_called_once()
    panel = mock_console.print.call_args[0][0]
    assert "patch_file" in panel.title
    assert "file.py" in panel.title


# ── display_file_status ───────────────────────────────────────────

@patch("utils.file_change_display.console")
def test_display_file_status_basic(mock_console):
    display_file_status("mkdir", "src/utils")
    mock_console.print.assert_called_once()
    rendered = str(mock_console.print.call_args[0][0])
    assert "mkdir" in rendered
    assert "src/utils" in rendered


@patch("utils.file_change_display.console")
def test_display_file_status_with_detail(mock_console):
    display_file_status("copy_file", "a.py", "→ b.py")
    mock_console.print.assert_called_once()
    rendered = str(mock_console.print.call_args[0][0])
    assert "copy_file" in rendered
    assert "→ b.py" in rendered
