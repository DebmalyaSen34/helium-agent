from catalog.cache import Cache
from catalog.repository import Product, Repository


class ProductService:
    def __init__(self, repository: Repository, cache: Cache | None = None):
        self.repository = repository
        self.cache = cache or Cache()

    def get_product(self, product_id: int) -> Product:
        key = f"product:{product_id}"
        product = self.cache.get(key)
        if product is None:
            product = self.repository.get(product_id)
            self.cache.set(key, product)
        return product

    def list_products(self) -> list[Product]:
        products = self.cache.get("products:all")
        if products is None:
            products = self.repository.all()
            self.cache.set("products:all", products)
        return products

    def update_price(self, product_id: int, price_cents: int) -> Product:
        if price_cents < 0:
            raise ValueError("price must not be negative")
        self.repository.set_price(product_id, price_cents)
        return self.get_product(product_id)
