from planner.board import Board
from planner.models import TaskList


def test_lists_do_not_share_tasks():
    a, b = TaskList("a"), TaskList("b")
    a.add("write report")
    assert len(a) == 1
    assert len(b) == 0


def test_lists_do_not_share_tags():
    a, b = TaskList("a"), TaskList("b")
    a.tag("urgent")
    assert b.tags == set()


def test_explicit_tasks_are_kept():
    assert TaskList("c", ["x", "y"]).tasks == ["x", "y"]


def test_board_lists_are_independent():
    board = Board()
    board.new_list("todo").add("one")
    assert len(board.new_list("done")) == 0
