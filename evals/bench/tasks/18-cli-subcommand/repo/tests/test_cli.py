from todo_cli.cli import main


def test_add_and_list(tmp_path, capsys):
    db = str(tmp_path / "todo.json")
    main(["--db", db, "add", "milk"])
    main(["--db", db, "list"])
    assert capsys.readouterr().out.splitlines() == ["Added 1: milk", "[ ] 1 milk"]
