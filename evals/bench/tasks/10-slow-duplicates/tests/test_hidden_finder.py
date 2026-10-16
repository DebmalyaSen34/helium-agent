import random
import time

from dedupe.finder import find_duplicates


def test_order_is_by_second_occurrence():
    assert find_duplicates(["a", "b", "b", "a", "c", "a", "c"]) == ["b", "a", "c"]


def test_no_duplicates_and_empty():
    assert find_duplicates([1, 2, 3]) == []
    assert find_duplicates([]) == []


def test_unhashable_is_not_required_but_mixed_types_work():
    assert find_duplicates([1, "1", 1, "1"]) == [1, "1"]


def test_large_input_is_fast():
    rng = random.Random(7)
    items = [rng.randrange(20_000) for _ in range(40_000)]
    started = time.perf_counter()
    result = find_duplicates(items)
    elapsed = time.perf_counter() - started
    seen, expected = set(), []
    counts = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
        if counts[item] == 2:
            expected.append(item)
    assert result == expected
    assert elapsed < 0.5, f"took {elapsed:.2f}s"
