"""The /coupang/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs). Every endpoint caches its own result
through cache.cached_call keyed on the validated params.

The three seller endpoints (details / products / categories) share ONE
cached store-page parse (store id + vendor id + name, _store_identity): a
client hitting all three on the same store pays one page fetch for the
identity, then one JSON call per endpoint.
"""
from cache import cached_call
from coupang import cache_config as ttl
from coupang import parsers, refs
from coupang import fetch as F


# ---- products/search -------------------------------------------------------------

def _search(query, sort, min_price, max_price, rocket_only):
    html = F.fetch_search_page(query, sort=sort, min_price=min_price, max_price=max_price, rocket_only=bool(rocket_only))
    out = parsers.parse_search(html)
    public_sort = next((k for k, v in refs.LISTING_SORTS.items() if v == (sort or "scoreDesc")), "ranking")
    return {"query": out["query"] or query, "sort": public_sort, "search_id": out["search_id"],
            "count": out["count"], "results": out["results"],
            "related_keywords": out["related_keywords"], "filters": out["filters"]}


def products_search(**data):
    return cached_call("coupang.search", data, _search, ttl.SEARCH_CACHE)


# ---- products/details ------------------------------------------------------------

def _details(product):
    html = F.fetch_product_page(product["product_id"], product.get("item_id"), product.get("vendor_item_id"))
    record = parsers.parse_product(html)
    if not record:
        raise F.CoupangNotFound(f"product {product['product_id']} not found")
    # a bare id opens the default option but streams the below-the-fold block
    # (seller, policies, essentials, description) lazily: load the option's own
    # link, which renders it server-side
    if not parsers.has_below_fold(html) and record.get("item_id") and record.get("vendor_item_id") \
            and not (product.get("item_id") and product.get("vendor_item_id")):
        try:
            full = parsers.parse_product(F.fetch_product_page(record["product_id"], record["item_id"], record["vendor_item_id"]))
        except (F.CoupangUpstreamError, F.CoupangNotFound, F.CoupangBadRequest):
            full = None
        record = full or record
    other = None
    if record.get("other_seller_count") and record.get("item_id") and record.get("vendor_item_id"):
        try:
            other = parsers.parse_other_sellers(F.fetch_other_sellers(record["product_id"], record["item_id"], record["vendor_item_id"]))
        except (F.CoupangUpstreamError, F.CoupangNotFound, F.CoupangBadRequest):
            other = None
    record["other_sellers"] = (other or {}).get("results") if other else None
    return record


def product_details(**data):
    return cached_call("coupang.product", data, _details, ttl.PRODUCT_CACHE)


# ---- products/reviews / products/questions ----------------------------------------

def _reviews(product, page, sort, rating):
    payload = F.fetch_reviews(product["product_id"], product.get("item_id"), product.get("vendor_item_id"), page=page,
                              sort_key=sort or refs.REVIEW_SORTS["best"], rating=rating)
    out = parsers.parse_reviews(payload, page)
    public_sort = next((k for k, v in refs.REVIEW_SORTS.items() if v == (sort or refs.REVIEW_SORTS["best"])), "best")
    return {"product_id": product["product_id"], "sort": public_sort, "rating_filter": rating, **out}


def product_reviews(**data):
    return cached_call("coupang.reviews", data, _reviews, ttl.REVIEWS_CACHE)


def _questions(product, page):
    payload = F.fetch_questions(product["product_id"], product.get("item_id"), product.get("vendor_item_id"), page=page)
    return {"product_id": product["product_id"], **parsers.parse_questions(payload, page)}


def product_questions(**data):
    return cached_call("coupang.questions", data, _questions, ttl.QUESTIONS_CACHE)


# ---- categories/products ---------------------------------------------------------

def _category_products(category, page, sort, min_price, max_price, rocket_only):
    html = F.fetch_category_page(category, page=page, sort=sort, min_price=min_price, max_price=max_price,
                                 rocket_only=bool(rocket_only))
    out = parsers.parse_category_page(html, page)
    public_sort = next((k for k, v in refs.LISTING_SORTS.items() if v == (sort or "scoreDesc")), "ranking")
    return {"category_id": category, "name": out["name"], "link": refs.category_link(category), "sort": public_sort,
            "breadcrumbs": out["breadcrumbs"], "results": out["results"], "filters": out["filters"],
            "pagination": out["pagination"]}


def category_products(**data):
    return cached_call("coupang.category_products", data, _category_products, ttl.CATEGORY_CACHE)


# ---- products/best / products/new / categories/best ---------------------------------

def _best(category, collection, page):
    cards = parsers.parse_best100(F.fetch_best100(category, collection, page))
    for card in cards:
        card["rank"] = (page - 1) * refs.BEST_PAGE_SIZE + card["rank"]
    info = refs.best_category(category)
    return {
        "category": {"id": info[0], "name": info[1], "slug": info[2], "link": f"{refs.SITE}/np/best100/{collection}/{info[0]}"} if info else None,
        "collection": collection,
        "results": cards,
        "pagination": {"page": page, "items_per_page": refs.BEST_PAGE_SIZE, "total_pages": refs.BEST_PAGES,
                       "total_count": refs.BEST_LIST_SIZE},
    }


def products_best(**data):
    return cached_call("coupang.best", data, _best, ttl.BEST_CACHE)


def _new():
    out = parsers.parse_todayopen(F.fetch_todayopen())
    return {"date": out["date"], "link": refs.SITE + "/np/todayopen", "count": out["count"],
            "total_new_today": out["total_count"], "results": out["results"]}


def products_new(**data):
    return cached_call("coupang.new", data, _new, ttl.NEW_CACHE)


def _home_best(category):
    # an empty `category=` reaches here as None (StrippedString), like "all"
    codes = None if category in (None, "all") else {category}
    units = parsers.parse_home_best(F.fetch_home_best(), codes)
    if codes and not units:
        raise F.CoupangUpstreamError(f"home unit {category} missing from Coupang's answer")
    return {"count": len(units), "categories": units}


def categories_best(**data):
    return cached_call("coupang.home_best", data, _home_best, ttl.HOME_BEST_CACHE)


# ---- categories/list / products/suggest ----------------------------------------------

def _categories():
    out = parsers.parse_category_list(F.fetch_category_list())
    out["best100_categories"] = [{"id": cid, "name": name, "slug": slug, "link": f"{refs.SITE}/np/best100/bestseller/{cid}"}
                                 for cid, name, slug in refs.BEST_CATEGORIES]
    return out


def categories_list(**data):
    return cached_call("coupang.categories", data, _categories, ttl.CATEGORIES_CACHE)


def _suggest(query):
    words = parsers.parse_suggestions(F.fetch_suggestions(query))
    return {"query": query, "count": len(words), "suggestions": words}


def products_suggest(**data):
    return cached_call("coupang.suggest", data, _suggest, ttl.SUGGEST_CACHE)


# ---- sellers ------------------------------------------------------------------------

def _identity(seller):
    page = parsers.parse_store_page(F.fetch_store_page(seller))
    if not page.get("store_id") or not page.get("vendor_id"):
        raise F.CoupangUpstreamError(f"store {seller}: the store page carried no store / vendor id")
    page["slug"] = page.get("slug") or seller
    return page


def _store_identity(seller):
    return cached_call("coupang.store_identity", {"seller": seller}, _identity, ttl.SELLER_CATEGORIES_CACHE)


def _seller_details(seller):
    store = _store_identity(seller)
    profile = parsers.parse_store_review(F.fetch_store_review(store["store_id"], store["vendor_id"], store["slug"]))
    followers = parsers.parse_store_follow(F.fetch_store_follow(store["store_id"]))
    top = parsers.parse_store_listing(F.fetch_store_top_selling(store["store_id"], store["vendor_id"]))
    return {
        "vendor_id": store["vendor_id"],
        "store_id": store["store_id"],
        "slug": store["slug"],
        "name": profile.get("name") or store.get("name"),
        "link": store.get("link") or refs.store_link(seller),
        "description": store.get("description"),
        "followers": followers,
        "product_count": top["pagination"]["total_count"] or None,
        "rating": {"count": profile["rating_count"], "thumbs_up": profile["thumbs_up"], "thumbs_down": profile["thumbs_down"],
                   "satisfaction_percent": profile["satisfaction_percent"]},
        "is_quality_seller": profile["is_quality_seller"],
        "business": {"representative": profile["representative"], "phone": profile["phone"], "email": profile["email"],
                     "address": profile["address"], "business_number": profile["business_number"]},
        "top_selling": top["results"],
    }


def seller_details(**data):
    return cached_call("coupang.seller", data, _seller_details, ttl.SELLER_CACHE)


def _seller_products(seller, page, sort, category):
    store = _store_identity(seller)
    payload = F.fetch_store_listing(store["store_id"], store["vendor_id"], page=page, sort_key=sort, category_id=category,
                                    url_name=store["slug"])
    out = parsers.parse_store_listing(payload, page)
    public_sort = next((k for k, v in refs.STORE_SORTS.items() if v == (sort or "POPULARITY")), "ranking")
    return {"vendor_id": store["vendor_id"], "store_id": store["store_id"], "name": store.get("name"), "sort": public_sort,
            "category_id": category, "results": out["results"], "pagination": out["pagination"]}


def seller_products(**data):
    return cached_call("coupang.seller_products", data, _seller_products, ttl.SELLER_PRODUCTS_CACHE)


def _seller_categories(seller):
    store = _store_identity(seller)
    out = parsers.parse_store_categories(F.fetch_store_main_category(store["vendor_id"]), F.fetch_store_filter(store["vendor_id"]))
    return {"vendor_id": store["vendor_id"], "store_id": store["store_id"], "name": store.get("name"), **out}


def seller_categories(**data):
    return cached_call("coupang.seller_categories", data, _seller_categories, ttl.SELLER_CATEGORIES_CACHE)
