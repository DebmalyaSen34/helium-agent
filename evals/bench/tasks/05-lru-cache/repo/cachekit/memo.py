import functools

from cachekit.lru import LRUCache

_MISSING = object()


def memoize(capacity: int = 128):
    def decorator(func):
        cache = LRUCache(capacity)

        @functools.wraps(func)
        def wrapper(*args):
            value = cache.get(args, _MISSING)
            if value is _MISSING:
                value = func(*args)
                cache.put(args, value)
            return value

        wrapper.cache = cache
        return wrapper

    return decorator
