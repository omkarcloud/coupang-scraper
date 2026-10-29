"""Every /coupang/* schema: the forms each param accepts (bare id, site
link, name), the forms it rejects, and the message a caller sees."""
import pytest
from marshmallow import ValidationError

from coupang import refs, schemas


def load(schema, **query):
    return schema().load({k: v for k, v in query.items() if v is not None})


def rejects(schema, field, **query):
    with pytest.raises(ValidationError) as info:
        load(schema, **query)
    messages = info.value.normalized_messages()
    assert field in messages, messages
    return " ".join(messages[field])


# ---- products/search -------------------------------------------------------------

def test_search_accepts_keywords_links_and_filters():
    data = load(schemas.SearchSchema, query="무선 마우스")
    assert data == {"query": "무선 마우스", "sort": None, "min_price": None, "max_price": None, "rocket_only": None}
    data = load(schemas.SearchSchema, query="https://www.coupang.com/np/search?q=%EB%AC%B4%EC%84%A0+%EB%A7%88%EC%9A%B0%EC%8A%A4&channel=user",
                sort="Price_Low", min_price="10000", max_price="30000", rocket_only="true")
    assert data["query"] == "무선 마우스" and data["sort"] == "salePriceAsc"
    assert data["min_price"] == 10000 and data["max_price"] == 30000 and data["rocket_only"] is True
    assert load(schemas.SearchSchema, query="logitech mouse", sort="newest")["sort"] == "latestAsc"


def test_search_rejects_bad_forms():
    assert "Must be one of" in rejects(schemas.SearchSchema, "sort", query="x", sort="cheapest")
    assert "min_price must not exceed" in rejects(schemas.SearchSchema, "max_price", query="x", min_price="50", max_price="10")
    assert rejects(schemas.SearchSchema, "query")
    assert "search keyword" in rejects(schemas.SearchSchema, "query", query="https://www.coupang.com/np/search?channel=user")
    assert "coupang.com" in rejects(schemas.SearchSchema, "query", query="https://www.gmarket.co.kr/n/search?keyword=x")
    assert "Must be true or false" in rejects(schemas.SearchSchema, "rocket_only", query="x", rocket_only="maybe")
    with pytest.raises(ValidationError):
        load(schemas.SearchSchema, query="x", page="2")       # no paging: the site serves one page


# ---- products/details / reviews / questions ---------------------------------------

def test_product_accepts_ids_and_links_with_the_option():
    assert load(schemas.ProductSchema, product="6982437348")["product"] == {
        "product_id": "6982437348", "item_id": None, "vendor_item_id": None}
    link = "https://www.coupang.com/vp/products/6982437348?itemId=18729357282&vendorItemId=85861963518&q=x&searchId=1"
    assert load(schemas.ProductSchema, product=link)["product"] == {
        "product_id": "6982437348", "item_id": "18729357282", "vendor_item_id": "85861963518"}
    assert load(schemas.ProductSchema, product="www.coupang.com/vp/products/6982437348")["product"]["product_id"] == "6982437348"
    assert load(schemas.ProductSchema, product="https://m.coupang.com/vm/products/6982437348?vendorItemId=85861963518")["product"] == {
        "product_id": "6982437348", "item_id": None, "vendor_item_id": "85861963518"}


def test_product_rejects_bad_forms():
    assert "product id" in rejects(schemas.ProductSchema, "product", product="abc")
    assert "product link" in rejects(schemas.ProductSchema, "product", product="https://www.coupang.com/np/search?q=x")
    assert "coupang.com" in rejects(schemas.ProductSchema, "product", product="https://www.amazon.com/dp/B0")
    assert rejects(schemas.ProductSchema, "product", product="  ")


def test_reviews_and_questions_paging():
    data = load(schemas.ReviewsSchema, product="6982437348", page="3", sort="Newest", rating="5")
    assert data["page"] == 3 and data["sort"] == "DATE_DESC" and data["rating"] == 5
    assert load(schemas.ReviewsSchema, product="6982437348")["sort"] is None
    assert "Must be one of" in rejects(schemas.ReviewsSchema, "sort", product="6982437348", sort="helpful")
    assert rejects(schemas.ReviewsSchema, "rating", product="6982437348", rating="6")
    assert rejects(schemas.ReviewsSchema, "page", product="6982437348", page="0")
    assert load(schemas.QuestionsSchema, product="6982437348", page="2")["page"] == 2


# ---- categories --------------------------------------------------------------------

def test_category_products_accepts_ids_and_links():
    data = load(schemas.CategoryProductsSchema, category="497135")
    assert data["category"] == "497135" and data["page"] == 1
    data = load(schemas.CategoryProductsSchema, category="https://www.coupang.com/np/categories/497135?page=3", page="2",
                sort="best_selling", min_price="100000")
    assert data["category"] == "497135" and data["page"] == 2 and data["sort"] == "saleCountDesc"
    assert "category id" in rejects(schemas.CategoryProductsSchema, "category", category="laptops")
    assert "category link" in rejects(schemas.CategoryProductsSchema, "category", category="https://www.coupang.com/vp/products/1")


def test_best_takes_the_fifteen_tabs_by_id_name_or_slug():
    assert load(schemas.BestSchema) == {"category": "all", "collection": "bestseller", "page": 1}
    assert load(schemas.BestSchema, category="178155")["category"] == "178155"
    assert load(schemas.BestSchema, category="가전디지털")["category"] == "178155"
    assert load(schemas.BestSchema, category="Electronics", collection="Trending", page="4")["collection"] == "trending"
    assert load(schemas.BestSchema, category="https://www.coupang.com/np/best100/bestseller/194176")["category"] == "194176"
    assert "best100 categories" in rejects(schemas.BestSchema, "category", category="497135")
    assert rejects(schemas.BestSchema, "page", page="5")
    assert "Must be one of" in rejects(schemas.BestSchema, "collection", collection="weekly")


def test_home_best_takes_unit_codes_or_titles():
    assert load(schemas.HomeBestSchema)["category"] == "all"
    assert load(schemas.HomeBestSchema, category="electronics")["category"] == "ELECTRONICS"
    assert load(schemas.HomeBestSchema, category="식품")["category"] == "FOOD"
    assert "home category codes" in rejects(schemas.HomeBestSchema, "category", category="178155")


def test_no_param_schemas_reject_unknown_params():
    assert load(schemas.NewSchema) == {} and load(schemas.CategoriesSchema) == {}
    with pytest.raises(ValidationError):
        load(schemas.NewSchema, page="2")


def test_suggest():
    assert load(schemas.SuggestSchema, query="노트")["query"] == "노트"
    assert rejects(schemas.SuggestSchema, "query", query="")


# ---- sellers ----------------------------------------------------------------------

def test_seller_accepts_vendor_ids_slugs_and_links():
    assert load(schemas.SellerSchema, seller="a00996727")["seller"] == "A00996727"
    assert load(schemas.SellerSchema, seller="cuckoo")["seller"] == "cuckoo"
    assert load(schemas.SellerSchema, seller="https://shop.coupang.com/A00996727/433885?locale=ko_KR")["seller"] == "A00996727"
    assert load(schemas.SellerSchema, seller="shop.coupang.com/cuckoo")["seller"] == "cuckoo"
    assert "shop.coupang.com" in rejects(schemas.SellerSchema, "seller", seller="https://www.coupang.com/vp/products/1")
    assert "vendor id" in rejects(schemas.SellerSchema, "seller", seller="6982437348")


def test_seller_products_paging_sort_and_category():
    data = load(schemas.SellerProductsSchema, seller="A00996727", page="2", sort="price_high", category="496759")
    assert data == {"seller": "A00996727", "page": 2, "sort": "HIGH_PRICE", "category": "496759"}
    assert load(schemas.SellerProductsSchema, seller="A00996727")["sort"] is None
    assert "store category id" in rejects(schemas.SellerProductsSchema, "category", seller="A00996727", category="pc")
    assert "Must be one of" in rejects(schemas.SellerProductsSchema, "sort", seller="A00996727", sort="rating")
    # an empty category is "not given", not a TypeError from the regexp validator
    assert load(schemas.SellerProductsSchema, seller="A00996727", category="")["category"] is None


def test_sort_tables_are_public_names():
    for table in (refs.LISTING_SORTS, refs.STORE_SORTS, refs.REVIEW_SORTS):
        assert all(k == k.lower() and "_" in k or k.isalpha() for k in table)
