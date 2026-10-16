from catalog.repository import Product, Repository
from catalog.service import ProductService


def make():
    repo = Repository([Product(1, "pen", 100), Product(2, "ink", 250)])
    return repo, ProductService(repo)


def test_reads_are_cached():
    repo, service = make()
    service.get_product(1)
    service.get_product(1)
    service.list_products()
    service.list_products()
    assert repo.queries == 2


def test_update_returns_new_price():
    _, service = make()
    service.get_product(1)
    assert service.update_price(1, 120).price_cents == 120
    assert service.get_product(1).price_cents == 120


def test_listing_sees_update():
    _, service = make()
    service.list_products()
    service.update_price(2, 300)
    assert [p.price_cents for p in service.list_products()] == [100, 300]


def test_other_products_stay_cached_after_update():
    repo, service = make()
    service.get_product(1)
    service.get_product(2)
    service.update_price(1, 150)
    before = repo.queries
    service.get_product(2)
    assert repo.queries == before


def test_cache_works_again_after_update():
    repo, service = make()
    service.update_price(1, 175)
    service.get_product(1)
    before = repo.queries
    service.get_product(1)
    service.list_products()
    service.list_products()
    assert repo.queries == before + 1
