from catalog.repository import Product, Repository
from catalog.service import ProductService


def test_get_product():
    service = ProductService(Repository([Product(1, "pen", 100)]))
    assert service.get_product(1).name == "pen"
