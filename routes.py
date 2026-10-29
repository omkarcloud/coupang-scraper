"""The 13 Coupang endpoints. Every path is served with and without the
`/coupang` prefix, so code generated against the hosted API on RapidAPI
(paths like /products/details) runs unchanged against this server.

Params are validated by the marshmallow schemas in coupang/schemas.py (ONE
param per input: `product` takes a product ID or link, `category` an ID or
link, `seller` a vendor ID, store slug or link, `query` a keyword or search
link); unknown params are rejected."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from coupang import api, schemas
from schema_fields import load_query
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The request query as unicode strings (bottle 0.12's .get() hands back
    latin-1 decoded bytes, so getunicode is mandatory)."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_link(path, params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "", False)}
    query["page"] = page
    scheme, host = request.urlparts.scheme, request.urlparts.netloc
    return f"{scheme}://{host}{path}?{urlencode(query, doseq=True)}"


def paginate(result, path, params):
    """Lift the `pagination` block into the flat shape the hosted API
    returns: count / per_page / current_page / total_pages / next / previous.
    A listing that publishes no total (category pages) sets `has_next` and
    leaves the totals null."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)
    page = _as_int(pagination.get("page")) or _as_int(params.get("page")) or 1
    if "has_next" in pagination:
        has_next = bool(pagination["has_next"])
        total_pages = pagination.get("total_pages")
        if total_pages is not None:
            total_pages = _as_int(total_pages, None)
    else:
        total_pages = max(_as_int(pagination.get("total_pages")), 0)
        has_next = page < total_pages
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(path, params, page + 1 if has_next else None),
        "previous": _page_link(path, params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(label, schema_cls, impl, paginated=False):
    """Validate, run, map errors: bad params -> 400, missing entity -> 404,
    blocks and transport failures -> 502 (retry with another proxy)."""
    raw = query_dict()
    data, error = load_query(schema_cls, raw)
    if error:
        return json_response(error, 400)
    try:
        result = impl(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response({"error": f"coupang rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Blocked as e:
        return json_response({"error": f"coupang blocked the request, retry later: {e}"}, 502)
    except UpstreamError as e:
        return json_response({"error": f"coupang {label} failed: {e}"}, 502)
    except Exception as e:                 # parser surprises
        return json_response({"error": f"coupang {label} failed: {type(e).__name__}: {e}"}, 500)
    if paginated:
        result = paginate(result, request.path, raw)
    return json_response(result)


ENDPOINTS = [
    ("/products/details", schemas.ProductSchema, api.product_details, False),
    ("/products/search", schemas.SearchSchema, api.products_search, False),
    ("/products/reviews", schemas.ReviewsSchema, api.product_reviews, True),
    ("/products/questions", schemas.QuestionsSchema, api.product_questions, True),
    ("/products/best", schemas.BestSchema, api.products_best, True),
    ("/products/new", schemas.NewSchema, api.products_new, False),
    ("/categories/products", schemas.CategoryProductsSchema, api.category_products, True),
    ("/categories/best", schemas.HomeBestSchema, api.categories_best, False),
    ("/categories/list", schemas.CategoriesSchema, api.categories_list, False),
    ("/sellers/details", schemas.SellerSchema, api.seller_details, False),
    ("/sellers/products", schemas.SellerProductsSchema, api.seller_products, True),
    ("/sellers/categories", schemas.SellerSchema, api.seller_categories, False),
    ("/products/suggest", schemas.SuggestSchema, api.products_suggest, False),
]


def mount(path, schema_cls, impl, paginated):
    """Serve a handler at /path and /coupang/path."""
    label = path.strip("/")

    def handler():
        return call(label, schema_cls, impl, paginated)

    handler.__name__ = "coupang_" + label.replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/coupang" + path, method="GET")(handler)


for _path, _schema, _impl, _paginated in ENDPOINTS:
    mount(_path, _schema, _impl, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
