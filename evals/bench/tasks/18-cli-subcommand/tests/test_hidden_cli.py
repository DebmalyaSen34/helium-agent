from todo_cli.cli import main


def setup(tmp_path, capsys):
    db = str(tmp_path / "todo.json")
    for title in ("milk", "eggs", "bread"):
        main(["--db", db, "add", title])
    capsys.readouterr()
    return db


def test_done_marks_task(tmp_path, capsys):
    db = setup(tmp_path, capsys)
    assert main(["--db", db, "done", "2"]) == 0
    assert capsys.readouterr().out.splitlines() == ["Completed 2: eggs"]
    main(["--db", db, "list"])
    assert capsys.readouterr().out.splitlines() == ["[ ] 1 milk", "[x] 2 eggs", "[ ] 3 bread"]


def test_pending_filter(tmp_path, capsys):
    db = setup(tmp_path, capsys)
    main(["--db", db, "done", "1"])
    capsys.readouterr()
    main(["--db", db, "list", "--pending"])
    assert capsys.readouterr().out.splitlines() == ["[ ] 2 eggs", "[ ] 3 bread"]


def test_unknown_id(tmp_path, capsys):
    db = setup(tmp_path, capsys)
    assert main(["--db", db, "done", "9"]) == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == "No task 9"
    assert captured.out == ""


def test_done_persists(tmp_path, capsys):
    db = setup(tmp_path, capsys)
    main(["--db", db, "done", "3"])
    main(["--db", db, "add", "jam"])
    capsys.readouterr()
    main(["--db", db, "list", "--pending"])
    assert capsys.readouterr().out.splitlines() == ["[ ] 1 milk", "[ ] 2 eggs", "[ ] 4 jam"]
