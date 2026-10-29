"""Reference resolvers + the fixed category tables for /coupang/*.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    product    a product id (6982437348) OR any coupang.com product link
               (/vp/products/<id>?itemId=&vendorItemId= — the option in the
               link is honoured; a bare id lands on the site's default option)
    category   a category id (497135) OR a /np/categories/<id> link
    seller     a vendor id (A00996727), a store slug (cuckoo) OR a
               shop.coupang.com store link
    query      a keyword OR a /np/search?q= link (its q)

Fixed tables (captured 2026-10-23/28 from the site): the 15 best100
category tabs (/np/best100/bestseller/<id>) and the 18 home "best by
category" codes (n-api/homeunit/BEST_CATEGORY?category=...). Resolvers raise
ValueError with a user-facing message (RefField turns it into a 400).
"""
import re
from urllib.parse import parse_qs, unquote, urlparse

SITE = "https://www.coupang.com"
SHOP = "https://shop.coupang.com"

PRODUCT_ID_RE = re.compile(r"^[0-9]{5,13}$")
CATEGORY_ID_RE = re.compile(r"^[0-9]{3,9}$")
VENDOR_ID_RE = re.compile(r"^A[0-9]{8}$", re.I)
STORE_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,60}$")

_LINK_PRODUCT_RE = re.compile(r"/v[pm]/products/([0-9]{5,13})(?:/|\?|#|$)")
_LINK_CATEGORY_RE = re.compile(r"/np/categories/([0-9]{3,9})(?:/|\?|#|$)")
_LINK_BEST_RE = re.compile(r"/np/best100/(?:bestseller|trending)/([0-9]{3,9})(?:/|\?|#|$)")
_LINK_STORE_RE = re.compile(r"^/([A-Za-z0-9][A-Za-z0-9_-]{1,60})(?:/[0-9]+)?/?$")

_HOSTS = ("coupang.com",)


def _is_link(value):
    low = value.lower()
    return low.startswith(("http://", "https://", "//", "www.coupang.com/", "coupang.com/", "shop.coupang.com/",
                           "m.coupang.com/"))


def _as_url(value):
    if value.startswith("//"):
        return "https:" + value
    if not value.lower().startswith(("http://", "https://")):
        return "https://" + value
    return value


def _host(url):
    return (urlparse(url).hostname or "").lower()


def _link(value, label):
    """The URL when `value` is a coupang.com link, None when it is not a
    link; ValueError for another site's link."""
    if not _is_link(value):
        return None
    url = _as_url(value)
    host = _host(url)
    if not (host == "coupang.com" or host.endswith(".coupang.com")):
        raise ValueError(f"Must be a coupang.com {label} link.")
    return url


def resolve_product(value):
    """Bare product id OR a coupang.com product link -> {"product_id",
    "item_id", "vendor_item_id"} (the two option ids only from a link that
    carries them; None = the site's default option)."""
    value = (value or "").strip()
    url = _link(value, "product")
    if url is None:
        if PRODUCT_ID_RE.match(value):
            return {"product_id": value, "item_id": None, "vendor_item_id": None}
        raise ValueError("Must be a Coupang product id (the number in a product link, e.g. 6982437348) "
                         "or a coupang.com product link (https://www.coupang.com/vp/products/<id>).")
    match = _LINK_PRODUCT_RE.search(urlparse(url).path)
    if not match:
        raise ValueError("Must be a coupang.com product link (https://www.coupang.com/vp/products/<id>).")
    query = parse_qs(urlparse(url).query)
    item_id = (query.get("itemId") or [None])[0]
    vendor_item_id = (query.get("vendorItemId") or [None])[0]
    return {"product_id": match.group(1),
            "item_id": item_id if item_id and item_id.isdigit() else None,
            "vendor_item_id": vendor_item_id if vendor_item_id and vendor_item_id.isdigit() else None}


def product_link(product_id, item_id=None, vendor_item_id=None):
    link = f"{SITE}/vp/products/{product_id}"
    if item_id and vendor_item_id:
        link += f"?itemId={item_id}&vendorItemId={vendor_item_id}"
    elif vendor_item_id:
        link += f"?vendorItemId={vendor_item_id}"
    return link


def resolve_category(value):
    """Bare category id OR a /np/categories/<id> (or best100 tab) link -> the id."""
    value = (value or "").strip()
    url = _link(value, "category")
    if url is None:
        if CATEGORY_ID_RE.match(value):
            return value
        raise ValueError("Must be a Coupang category id (the number in a category link, e.g. 497135) "
                         "or a coupang.com category link (https://www.coupang.com/np/categories/<id>).")
    path = urlparse(url).path
    match = _LINK_CATEGORY_RE.search(path) or _LINK_BEST_RE.search(path)
    if match:
        return match.group(1)
    raise ValueError("Must be a coupang.com category link (https://www.coupang.com/np/categories/<id>).")


def category_link(category_id):
    return f"{SITE}/np/categories/{category_id}"


def resolve_seller(value):
    """A vendor id (A00996727), a store slug OR a shop.coupang.com store link
    -> the store path segment the site uses (vendor id or slug, as given)."""
    value = (value or "").strip()
    url = _link(value, "store")
    if url is None:
        if VENDOR_ID_RE.match(value):
            return value.upper()
        if STORE_SLUG_RE.match(value) and not PRODUCT_ID_RE.match(value):
            return value
        raise ValueError("Must be a Coupang vendor id (A00996727), a store slug (cuckoo) "
                         "or a shop.coupang.com store link (https://shop.coupang.com/<vendor id or slug>).")
    if _host(url) != "shop.coupang.com":
        raise ValueError("Must be a shop.coupang.com store link (https://shop.coupang.com/<vendor id or slug>).")
    match = _LINK_STORE_RE.match(urlparse(url).path)
    if match and match.group(1).lower() not in ("api", "vid", "static", "assets"):
        seg = match.group(1)
        return seg.upper() if VENDOR_ID_RE.match(seg) else seg
    raise ValueError("Must be a shop.coupang.com store link (https://shop.coupang.com/<vendor id or slug>).")


def store_link(seller):
    return f"{SHOP}/{seller}"


def resolve_query(value):
    """A keyword, or a coupang.com search link -> its `q`."""
    value = (value or "").strip()
    if not _is_link(value):
        return value
    url = _link(value, "search")
    query = parse_qs(urlparse(url).query)
    term = unquote((query.get("q") or [""])[0]).strip()
    if term:
        return term
    raise ValueError("Must be a search keyword or a coupang.com search link (https://www.coupang.com/np/search?q=...).")


# ---- fixed tables ---------------------------------------------------------------

# The best100 category tabs (/np/best100/bestseller/<id>), captured
# 2026-10-23 from the rendered page. n-api/best100/products accepts any
# componentId and silently falls back for an unknown one, so the API only
# takes these.
BEST_CATEGORIES = (
    ("564553", "패션의류/잡화", "fashion"),
    ("176422", "뷰티", "beauty"),
    ("221834", "출산/유아동", "baby"),
    ("194176", "식품", "food"),
    ("185569", "주방용품", "kitchen"),
    ("115573", "생활용품", "living"),
    ("184455", "홈인테리어", "home-interior"),
    ("178155", "가전디지털", "electronics"),
    ("317678", "스포츠/레저", "sports"),
    ("183960", "자동차용품", "car"),
    ("317677", "도서", "books"),
    ("317679", "완구/취미", "toys-hobby"),
    ("177195", "문구/오피스", "office"),
    ("115574", "반려/애완", "pets"),
    ("305698", "헬스/건강식품", "health"),
)
_BEST_BY_ID = {cid: (cid, name, slug) for cid, name, slug in BEST_CATEGORIES}
_BEST_BY_KEY = {}
for _cid, _name, _slug in BEST_CATEGORIES:
    _BEST_BY_KEY[_cid] = _BEST_BY_KEY[_name] = _BEST_BY_KEY[_slug] = _BEST_BY_ID[_cid]
    _BEST_BY_KEY[_slug.replace("-", "_")] = _BEST_BY_ID[_cid]


def resolve_best_category(value):
    """One of the 15 best100 tabs, by id, Korean name, English slug or a
    /np/best100/bestseller/<id> link -> the id. "all" / empty = every category."""
    value = (value or "").strip()
    if not value or value.lower() == "all":
        return "all"
    key = value
    if _is_link(value):
        url = _link(value, "best100")
        match = _LINK_BEST_RE.search(urlparse(url).path) or _LINK_CATEGORY_RE.search(urlparse(url).path)
        if not match:
            raise ValueError("Must be a coupang.com best100 link (https://www.coupang.com/np/best100/bestseller/<id>).")
        key = match.group(1)
    hit = _BEST_BY_KEY.get(key) or _BEST_BY_KEY.get(key.lower())
    if hit:
        return hit[0]
    raise ValueError("Must be one of the best100 categories: all, "
                     + ", ".join(f"{slug} ({name}, {cid})" for cid, name, slug in BEST_CATEGORIES) + ".")


def best_category(category_id):
    """(id, Korean name, slug) for a best100 category id, or None for "all"."""
    return _BEST_BY_ID.get(category_id)


# The home page "best by category" units (n-api/homeunit/BEST_CATEGORY),
# captured 2026-10-28: the request code, the unit title and the category
# page each unit links to.
HOME_CATEGORIES = (
    ("WOMAN_CLOTHE", "여성패션", "564653"),
    ("MAN_CLOTHE", "남성패션", "187069"),
    ("BEAUTY", "뷰티", "176522"),
    ("BABY", "출산/유아동", "221934"),
    ("FOOD", "식품", "194276"),
    ("KITCHEN", "주방용품", "185669"),
    ("LIVING", "생활용품", "115673"),
    ("FURNITURE", "홈인테리어", "184555"),
    ("ELECTRONICS", "가전디지털", "178255"),
    ("SPORTS", "스포츠/레저", "317778"),
    ("CAR", "자동차용품", "184060"),
    ("HOBBY", "완구/취미", "317779"),
    ("OFFICE", "문구/오피스", "177295"),
    ("BOOKS", "도서/음반/DVD", "317777"),
    ("PETS", "반려동물용품", "115674"),
    ("TRAVEL", "여행/티켓", "0"),
    ("BABY_FASHION", "유아동패션", "0"),
    ("HEALTH", "헬스/건강식품", "305798"),
)
_HOME_BY_KEY = {}
for _code, _title, _cat in HOME_CATEGORIES:
    _HOME_BY_KEY[_code] = _HOME_BY_KEY[_code.lower()] = _HOME_BY_KEY[_title] = _code


def resolve_home_category(value):
    """One of the 18 home "best by category" units, by code (ELECTRONICS,
    case-insensitive) or Korean title -> the code. Empty / "all" = all 18."""
    value = (value or "").strip()
    if not value or value.lower() == "all":
        return "all"
    code = _HOME_BY_KEY.get(value) or _HOME_BY_KEY.get(value.lower()) or _HOME_BY_KEY.get(value.upper())
    if code:
        return code
    raise ValueError("Must be one of the home category codes: all, "
                     + ", ".join(f"{code} ({title})" for code, title, _ in HOME_CATEGORIES) + ".")


# Search / category listing sorts: public name -> the site's `sorter`
# (search; `bestAsc` is the category page's name for the default order).
LISTING_SORTS = {
    "ranking": "scoreDesc",
    "price_low": "salePriceAsc",
    "price_high": "salePriceDesc",
    "best_selling": "saleCountDesc",
    "newest": "latestAsc",
}
# Seller store listing sorts (shop.coupang.com/api/v1/listing SORT_KEY,
# from the store's own filter list, 2026-10-28).
STORE_SORTS = {
    "ranking": "POPULARITY",
    "price_low": "LOW_PRICE",
    "price_high": "HIGH_PRICE",
    "best_selling": "BEST_SELLING",
    "newest": "LATEST",
}
# Review sorts (next-api/review sortBy).
REVIEW_SORTS = {
    "best": "ORDER_SCORE_ASC",
    "newest": "DATE_DESC",
}
BEST_COLLECTIONS = ("bestseller", "trending")

SEARCH_PAGE_SIZE = 60        # what an anonymous search answers (listSize is ignored)
CATEGORY_PAGE_SIZE = 60      # /np/categories/<id> default; listSize=120 is honoured
BEST_PAGE_SIZE = 30          # n-api/best100/products: 30 a page, 4 pages
BEST_PAGES = 4
BEST_LIST_SIZE = 100         # the list holds 100 (page 4 carries 10), not 4 x 30
STORE_PAGE_SIZE = 20         # shop.coupang.com/api/v1/listing
REVIEW_PAGE_SIZE = 10
QUESTION_PAGE_SIZE = 15      # next-api/products/inquiries?isPreview=false
