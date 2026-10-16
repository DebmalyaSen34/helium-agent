import pytest

from shop.catalog import catalog_page
from shop.pagination import page_count, paginate


def test_first_page_starts_at_first_item():
    assert paginate(list(range(10)), 1, 3) == [0, 1, 2]


def test_last_partial_page():
    assert paginate(list(range(10)), 4, 3) == [9]
    assert paginate(list(range(10)), 5, 3) == []


def test_page_count_rounds_up():
    assert page_count(10, 3) == 4
    assert page_count(9, 3) == 3
    assert page_count(0, 3) == 0
    assert page_count(1, 50) == 1


def test_invalid_arguments_still_rejected():
    with pytest.raises(ValueError):
        paginate([1], 0, 3)


def test_catalog_end_to_end():
    first = catalog_page(1)
    assert first["items"][0] == "product-1"
    assert first["pages"] == 5
    assert catalog_page(5)["items"] == ["product-21", "product-22", "product-23"]
