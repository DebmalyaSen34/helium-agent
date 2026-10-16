def paginate(items: list, page: int, per_page: int) -> list:
    """Return the items on `page`. Pages are numbered from 1."""
    if page < 1 or per_page < 1:
        raise ValueError("page and per_page must be at least 1")
    start = (page - 1) * per_page
    return items[start:start + per_page]


def page_count(total: int, per_page: int) -> int:
    """How many pages are needed to show `total` items."""
    return -(-total // per_page)
