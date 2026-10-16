from shop.pagination import page_count, paginate

PRODUCTS = [f"product-{n}" for n in range(1, 24)]


def catalog_page(page: int, per_page: int = 5) -> dict:
    return {
        "page": page,
        "pages": page_count(len(PRODUCTS), per_page),
        "items": paginate(PRODUCTS, page, per_page),
    }
