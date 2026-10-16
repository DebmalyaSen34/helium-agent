from collections import OrderedDict
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
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self.capacity = capacity
        self.evictions = 0
        self._data: OrderedDict = OrderedDict()

    def get(self, key: Hashable, default: Any = None) -> Any:
        if key not in self._data:
            return default
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: Hashable, value: Any) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        if len(self._data) > self.capacity:
            self._data.popitem(last=False)
            self.evictions += 1

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data
