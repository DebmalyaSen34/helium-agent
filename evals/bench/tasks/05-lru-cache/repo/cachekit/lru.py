from typing import Any, Hashable


class LRUCache:
    """A fixed-size cache that evicts the least recently used entry.

    - `capacity` must be a positive integer, otherwise ValueError.
    - `get(key, default=None)` returns the value (or `default`) and marks the key
      as most recently used when present.
    - `put(key, value)` inserts or updates the key and marks it most recently used.
      When the cache is over capacity, the least recently used key is evicted.
    - `len(cache)` is the number of entries; `key in cache` checks presence without
      changing recency.
    - `evictions` counts how many entries have been evicted so far.
    """

    def __init__(self, capacity: int):
        raise NotImplementedError

    def get(self, key: Hashable, default: Any = None) -> Any:
        raise NotImplementedError

    def put(self, key: Hashable, value: Any) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def __contains__(self, key: object) -> bool:
        raise NotImplementedError
