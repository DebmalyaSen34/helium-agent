import pytest

from tools import file_ops
from tools.edit_journal import JOURNAL, EditJournal


@pytest.fixture
def project(tmp_path):
    original = file_ops.PROJECT_ROOT
    file_ops.set_project_root(tmp_path)
    JOURNAL.clear()
    yield tmp_path
    JOURNAL.clear()
    file_ops.set_project_root(original)


def test_undo_restores_overwritten_file(project):
    (project / "a.txt").write_text("before")
    file_ops.write_file("a.txt", "after")
    result = JOURNAL.undo()
    assert result is not None and "write_file" in result.label
    assert (project / "a.txt").read_text() == "before"


def test_undo_removes_created_file(project):
    file_ops.write_file("new.txt", "hi")
    JOURNAL.undo()
    assert not (project / "new.txt").exists()


def test_undo_restores_deleted_directory(project):
    (project / "pkg").mkdir()
    (project / "pkg" / "m.py").write_text("x = 1")
    file_ops.delete_file("pkg", recursive=True)
    assert not (project / "pkg").exists()
    JOURNAL.undo()
    assert (project / "pkg" / "m.py").read_text() == "x = 1"


def test_undo_reverses_move(project):
    (project / "a.txt").write_text("data")
    file_ops.move_file("a.txt", "b.txt")
    JOURNAL.undo()
    assert (project / "a.txt").read_text() == "data"
    assert not (project / "b.txt").exists()


def test_undo_edit_file_and_mkdir_parents(project):
    (project / "c.py").write_text("v = 1\n")
    file_ops.edit_file("c.py", [{"old": "v = 1", "new": "v = 2"}])
    file_ops.mkdir("deep/nested/dir")
    JOURNAL.undo()
    assert not (project / "deep").exists()
    JOURNAL.undo()
    assert (project / "c.py").read_text() == "v = 1\n"


def test_failed_operation_is_not_journaled(project):
    result = file_ops.edit_file("missing.py", [{"old": "a", "new": "b"}])
    assert "status: error" in result
    assert len(JOURNAL) == 0
    assert JOURNAL.undo() is None


def test_group_cap_drops_oldest(tmp_path):
    journal = EditJournal(max_groups=2)
    for name in ("a", "b", "c"):
        journal.commit(journal.snapshot(name, [tmp_path / name]))
    assert len(journal) == 2
    assert journal.peek_label() == "c"
