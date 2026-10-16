from dedupe.finder import find_duplicates


def test_simple():
    assert find_duplicates([1, 2, 1]) == [1]
