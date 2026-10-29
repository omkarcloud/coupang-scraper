"""Marshmallow request schemas for every /coupang/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair): every id-shaped param also takes the coupang.com link of
the same record (coupang/refs.py resolvers).

    query       a search keyword OR a coupang.com search link (its q)
    product     a product id OR a product link (a link's itemId /
                vendorItemId pick the option; a bare id = the default option)
    category    a category id OR a /np/categories/<id> link
                (products/best: one of the 15 best100 tabs by id, Korean
                name or English slug; categories/best: a home unit code)
    seller      a vendor id (A00996727), a store slug OR a shop.coupang.com link
"""
import re

from marshmallow import ValidationError, validates_schema

from schema_fields import BaseSchema, ChoiceField, Flag, PageField, PositiveInt, Price, QueryField, RefField, StrippedString
from coupang import refs

REVIEW_MAX_PAGE = 1000        # 10 a page; the site serves any page (empty past the end)
QUESTION_MAX_PAGE = 500
CATEGORY_MAX_PAGE = 100       # 60 a page; the site keeps serving distinct pages (page 10 verified)
SELLER_MAX_PAGE = 500         # 20 a page


class ProductRefField(RefField):
    resolver = staticmethod(refs.resolve_product)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category)


class BestCategoryField(RefField):
    resolver = staticmethod(refs.resolve_best_category)


class HomeCategoryField(RefField):
    resolver = staticmethod(refs.resolve_home_category)


class SellerRefField(RefField):
    resolver = staticmethod(refs.resolve_seller)


class SearchQueryField(QueryField):
    """Search keyword or a coupang.com search link (its q)."""

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        try:
            return refs.resolve_query(value)
        except ValueError as e:
            raise ValidationError(str(e))


class _PriceRangeSchema(BaseSchema):
    """min_price <= max_price when both are given."""
    min_price = Price(metadata={"description": "lowest price to include, in KRW"})
    max_price = Price(metadata={"description": "highest price to include, in KRW"})

    @validates_schema
    def _price_range(self, data, **kwargs):
        low, high = data.get("min_price"), data.get("max_price")
        if low is not None and high is not None and low > high:
            raise ValidationError("min_price must not exceed max_price.", "max_price")


class SearchSchema(_PriceRangeSchema):
    query = SearchQueryField(metadata={"description": "search keyword (Korean matches best), or a coupang.com search link"})
    sort = ChoiceField(refs.LISTING_SORTS, metadata={
        "description": "result order: ranking (Coupang's own, default), price_low, price_high, best_selling, newest"})
    rocket_only = Flag(metadata={
        "description": "true = only Rocket (Coupang-fulfilled) deliveries: Rocket, Rocket Luxury and Rocket Global"})


class ProductSchema(BaseSchema):
    product = ProductRefField(metadata={
        "description": "product id (6982437348) or a coupang.com product link; a link's itemId / vendorItemId select the option"})


class ReviewsSchema(BaseSchema):
    product = ProductRefField(metadata={"description": "product id or a coupang.com product link"})
    page = PageField(max_page=REVIEW_MAX_PAGE, metadata={"description": "page of 10 reviews (1-based)"})
    sort = ChoiceField(refs.REVIEW_SORTS, metadata={"description": "best (Coupang's ranking, default) or newest"})
    rating = PositiveInt(max_value=5, metadata={"description": "only reviews with this star rating (1-5)"})


class QuestionsSchema(BaseSchema):
    product = ProductRefField(metadata={"description": "product id or a coupang.com product link"})
    page = PageField(max_page=QUESTION_MAX_PAGE, metadata={"description": "page of 15 questions (1-based)"})


class CategoryProductsSchema(_PriceRangeSchema):
    category = CategoryRefField(metadata={"description": "category id (497135) or a coupang.com category link"})
    page = PageField(max_page=CATEGORY_MAX_PAGE, metadata={"description": "page of 60 products (1-based)"})
    sort = ChoiceField(refs.LISTING_SORTS, metadata={
        "description": "product order: ranking (default), price_low, price_high, best_selling, newest"})
    rocket_only = Flag(metadata={"description": "true = only Rocket deliveries"})


class BestSchema(BaseSchema):
    category = BestCategoryField(required=False, load_default="all", metadata={
        "description": "one of the 15 best100 categories by id, Korean name or slug (electronics, food, beauty, ...); "
                       "all (default) = across every category"})
    collection = ChoiceField(refs.BEST_COLLECTIONS, load_default="bestseller", metadata={
        "description": "bestseller (the last 7 days' sales, default) or trending"})
    page = PageField(max_page=refs.BEST_PAGES, metadata={"description": "page of 30 (1-4; the list holds 100)"})


class NewSchema(BaseSchema):
    """No parameters: today's new arrivals are one server-rendered page."""


class CategoriesSchema(BaseSchema):
    """No parameters: the whole category tree."""


class HomeBestSchema(BaseSchema):
    category = HomeCategoryField(required=False, load_default="all", metadata={
        "description": "one home category unit by code (ELECTRONICS, FOOD, BEAUTY, ...) or Korean title; all (default) = every unit"})


class SuggestSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "the beginning of a search term (Korean or English)"})


class SellerSchema(BaseSchema):
    seller = SellerRefField(metadata={"description": "vendor id (A00996727), store slug (cuckoo) or a shop.coupang.com store link"})


def _store_category_id(value):
    """StrippedString hands an empty `category=` on as None (= not given);
    marshmallow still runs the validators on it, and Regexp would raise a
    TypeError (a bottle 500) instead of letting it through."""
    if value is not None and not re.fullmatch(r"[0-9]{1,12}", value):
        raise ValidationError("Must be a store category id (digits).")


class SellerProductsSchema(BaseSchema):
    seller = SellerRefField(metadata={"description": "vendor id, store slug or a shop.coupang.com store link"})
    page = PageField(max_page=SELLER_MAX_PAGE, metadata={"description": "page of 20 products (1-based)"})
    sort = ChoiceField(refs.STORE_SORTS, metadata={
        "description": "product order: ranking (default), price_low, price_high, best_selling, newest"})
    category = StrippedString(load_default=None, validate=_store_category_id,
                              metadata={"description": "one of the store's category ids (sellers/categories) to narrow the catalogue"})
