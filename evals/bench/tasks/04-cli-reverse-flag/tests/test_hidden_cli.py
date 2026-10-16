from wordcount.cli import main

TEXT = "b a c b a b d d e"  # b=3, a=2, d=2, c=1, e=1


def run(tmp_path, capsys, *flags):
    path = tmp_path / "words.txt"
    path.write_text(TEXT)
    assert main([str(path), *flags]) == 0
    return capsys.readouterr().out.split("\n")[:-1]


def test_default_order_unchanged(tmp_path, capsys):
    assert run(tmp_path, capsys) == ["b 3", "a 2", "d 2", "c 1", "e 1"]


def test_reverse_lists_rarest_first_with_alphabetical_ties(tmp_path, capsys):
    assert run(tmp_path, capsys, "--reverse") == ["c 1", "e 1", "a 2", "d 2", "b 3"]


def test_reverse_respects_top(tmp_path, capsys):
    assert run(tmp_path, capsys, "--reverse", "--top", "3") == ["c 1", "e 1", "a 2"]
