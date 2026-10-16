from shop.catalog import catalog_page


def test_catalog_page_has_metadata():
    result = catalog_page(2)
    assert result["page"] == 2
    assert "items" in result
