from planner.board import Board


def test_new_list_is_registered():
    board = Board()
    todo = board.new_list("todo")
    assert board.lists["todo"] is todo
