import pytest

from cachekit import LRUCache
from cachekit.memo import memoize


def test_basic_get_put():
    cache = LRUCache(2)
    cache.put("a", 1)
    assert cache.get("a") == 1
    assert cache.get("missing") is None
    assert cache.get("missing", 0) == 0


def test_evicts_least_recently_used():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")
    cache.put("c", 3)
    assert "b" not in cache
    assert "a" in cache and "c" in cache
    assert cache.evictions == 1


def test_update_refreshes_recency_without_growing():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)
    cache.put("c", 3)
    assert len(cache) == 2
    assert cache.get("a") == 10
    assert "b" not in cache


def test_contains_does_not_refresh():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert "a" in cache
    cache.put("c", 3)
    assert "a" not in cache


def test_falsy_values_are_cached():
    cache = LRUCache(1)
    cache.put("zero", 0)
    assert cache.get("zero", "default") == 0


@pytest.mark.parametrize("capacity", [0, -1])
def test_capacity_must_be_positive(capacity):
    with pytest.raises(ValueError):
        LRUCache(capacity)


def test_memoize_uses_cache():
    calls = []

    @memoize(capacity=2)
    def square(n):
        calls.append(n)
        return n * n

    assert [square(2), square(2), square(3)] == [4, 4, 9]
    assert calls == [2, 3]
