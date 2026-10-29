"""Coupang transport: plain curl_cffi for the surfaces Akamai leaves open,
a Korean residential curl session for the seller-store JSON, and page
navigations in a headed Chrome on the browser box (recipes/coupang.py)
for everything the site walls. No account, no cookies kept on GKE.

Why this shape (research 2026-10-23/24, proof from the pod 2026-10-28,
tools/egress_probe.py --via-pod --country kr, 12 surfaces):

  * OPEN to curl from the pod's own IP (and every other tier):
      n-api/best100/products                 best sellers, 30 a page, 4 pages per category
      /np/todayopen                          today's new arrivals (48 cards, server-rendered)
      n-api/homeunit/BEST_CATEGORY           the home page's best-by-category units
      n-api/web-adapter/category-list        the full category tree
      n-api/web-adapter/search?keyword=      search suggestions
      shop.coupang.com/<vendor>              store pages, follow count, top sellers,
                                             main categories, filters (JSON)
  * OPEN on a Korean residential exit only (Coupang's own 403
    "사용권한이 없습니다" from the pod's IP and from datacenter exits):
      shop.coupang.com/api/v1/sub/getStoreFollowInfo, api/v2/store/top_selling,
      api/v1/main_category, api/v1/filter
  * SELLER JSON THAT NEEDS THE PAGE'S OWN SENSOR (bare curl is Coupang's own
    403 on the pod IP, datacenter and — since 2026-10-29 — KR residential
    too; a Chrome's cookies replayed over curl on the same exit pass the
    first calls and are cut off after a few; an in-page fetch on a parked
    store page of the box browser keeps passing):
      shop.coupang.com/api/v1/store/getStoreReview   the seller profile
      shop.coupang.com/api/v1/listing                a store's catalogue page
  * WALLED for every curl identity on every tier (Akamai Bot Manager:
    "Access Denied" or the behavioural challenge page; a browser's cookie
    jar replayed over curl fails on any proxied exit too):
      /np/search, /np/categories/<id>, /vp/products/<id> and the product
      page's own JSON (next-api/review, next-api/products/inquiries,
      other-seller-info). These load as top-level navigations of a headed
      Chrome on a sticky Korean residential exit (the box's own German IP
      and datacenter exits are refused; Mac A/B 2026-10-24: a
      Chrome whose timezone/locale come from the process passes, one with
      Playwright's CDP emulation is cut off after a page). The product
      JSON is an in-page fetch on that product's own page.

Egress knobs (config): COUPANG_EXIT (open www surfaces, "direct"),
COUPANG_SELLER_EXIT (shop.coupang.com, "kr"), COUPANG_BROWSER_EXIT (the box
browsers, "kr"). One sticky exit per thread session, dropped on every
retryable failure; browser_client.ExitPool("coupang", ...) for the box
browsers, rotated on a refusal.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  CoupangUpstreamError  transport failure / 5xx / box unavailable           — retryable
  CoupangBlocked        Akamai 403 / challenge, Coupang's own 403, review   — retryable on a fresh exit
                        service refusal (RET9999), box refusal
  CoupangBadRequest     upstream 400                                       — never retried
  CoupangNotFound       unknown product / store / page                     — never retried
"""
import json
import os
import sys
import threading
import time
from urllib.parse import quote, urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import browser_client
import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from coupang import parsers, refs
from coupang.refs import SHOP, SITE

IMPERSONATE = "chrome"
WWW_TIMEOUT = 30
SHOP_TIMEOUT = 30
BOX_SITE = "coupang"
PAGE_HEADER = "x-coupang-page"     # the product page an in-page JSON fetch must run on

WWW_JSON_HEADERS = {"accept": "application/json, text/plain, */*", "referer": SITE + "/"}
WWW_PAGE_HEADERS = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "upgrade-insecure-requests": "1"}
SHOP_PAGE_HEADERS = dict(WWW_PAGE_HEADERS)
SHOP_JSON_HEADERS = {"accept": "application/json, text/plain, */*", "origin": SHOP, "referer": SHOP + "/",
                     "x-requested-with": "XMLHttpRequest"}
BOX_PAGE_HEADERS = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
BOX_JSON_HEADERS = {"accept": "application/json, text/plain, */*"}

HOME_CATEGORY_CODES = ",".join(code for code, _, _ in refs.HOME_CATEGORIES)


class CoupangUpstreamError(UpstreamError):
    """Transport failure, 5xx, a box outage or a malformed answer — retryable."""


class CoupangBlocked(CoupangUpstreamError, Blocked):
    """Akamai's 403 / challenge, Coupang's own 403, the review service's RET9999, or the box refusing the exit — retryable on a fresh exit."""


class CoupangBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class CoupangNotFound(NotFound):
    """Product / store / page does not exist — never retried."""


# ---- curl sessions ---------------------------------------------------------------
# One session per cheroot worker thread and per egress kind ("www": the
# open www.coupang.com surfaces on COUPANG_EXIT; "shop": shop.coupang.com on
# COUPANG_SELLER_EXIT). A curl handle must not cross threads; keep-alive
# within the thread; dropped on every retryable failure so the retry rides
# a fresh exit.

_local = threading.local()
_PROXY_FOR = {"www": lambda: config.coupang_proxy(), "shop": lambda: config.coupang_seller_proxy()}


def _session(kind):
    sessions = getattr(_local, "sessions", None)
    if sessions is None:
        sessions = _local.sessions = {}
    sess = sessions.get(kind)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = _PROXY_FOR[kind]()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        sess.headers["accept-language"] = egress.accept_language(proxy)
        sessions[kind] = sess
    return sess


def _drop_session(kind):
    sessions = getattr(_local, "sessions", None) or {}
    sess = sessions.pop(kind, None)
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn, kind):
    """Run fn() under the shared retry policy (CoupangUpstreamError only;
    NotFound / BadRequest surface immediately)."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except CoupangUpstreamError as e:
            last = e
            _drop_session(kind)
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _classify(resp, label):
    """Map an HTTP response to the error taxonomy; return the body text."""
    text = resp.text or ""
    if resp.status_code in (401, 403, 429) or parsers.is_blocked(text):
        raise CoupangBlocked(f"HTTP {resp.status_code} on {label}")
    if resp.status_code == 404:
        raise CoupangNotFound(f"{label} not found")
    if resp.status_code == 400:
        raise CoupangBadRequest(text[:200])
    if resp.status_code != 200:
        raise CoupangUpstreamError(f"HTTP {resp.status_code} on {label}")
    return text


def _json_or_raise(text, label):
    try:
        return json.loads(text)
    except ValueError:
        raise CoupangBlocked(f"non-JSON answer on {label}: {text[:120]!r}")


def _get(kind, url, label, headers, timeout, as_json):
    def once():
        try:
            resp = _session(kind).get(url, headers=headers, timeout=timeout)
        except Exception as e:
            raise CoupangUpstreamError(f"request failed: {type(e).__name__}: {e}")
        text = _classify(resp, label)
        return _json_or_raise(text, label) if as_json else text
    return _retrying(once, kind)


def _post_json(kind, url, body, label, headers, timeout):
    def once():
        try:
            resp = _session(kind).post(url, json=body, headers=headers, timeout=timeout)
        except Exception as e:
            raise CoupangUpstreamError(f"request failed: {type(e).__name__}: {e}")
        text = _classify(resp, label)
        payload = _json_or_raise(text, label)
        if isinstance(payload, dict) and payload.get("code") not in (None, 200):
            raise CoupangUpstreamError(f"{label}: shop answered code {payload.get('code')} {payload.get('msg')!r}")
        return payload
    return _retrying(once, kind)


# ---- open www.coupang.com surfaces (curl) ------------------------------------------

def fetch_best100(category_id="all", collection="bestseller", page=1):
    """n-api/best100/products -> the JSON (30 cards; page 5 is empty)."""
    params = {"collection": collection, "componentId": category_id or "all", "page": int(page)}
    return _get("www", f"{SITE}/n-api/best100/products?{urlencode(params)}", f"best100 {category_id} p{page}",
                {**WWW_JSON_HEADERS, "referer": SITE + "/np/best100"}, WWW_TIMEOUT, as_json=True)


def fetch_todayopen():
    """/np/todayopen -> the page HTML (its page param is ignored by the site)."""
    return _get("www", SITE + "/np/todayopen", "today's new products", WWW_PAGE_HEADERS, WWW_TIMEOUT, as_json=False)


def fetch_home_best():
    """n-api/homeunit/BEST_CATEGORY -> the JSON for all 18 category units (~1 MB)."""
    url = f"{SITE}/n-api/homeunit/BEST_CATEGORY?sort=false&category={HOME_CATEGORY_CODES}"
    return _get("www", url, "home best by category", WWW_JSON_HEADERS, WWW_TIMEOUT, as_json=True)


def fetch_category_list():
    """n-api/web-adapter/category-list -> the JSON category tree."""
    return _get("www", SITE + "/n-api/web-adapter/category-list", "category list", WWW_JSON_HEADERS, WWW_TIMEOUT,
                as_json=True)


def fetch_suggestions(keyword):
    """n-api/web-adapter/search?keyword= -> [{keyword}, ...]."""
    return _get("www", f"{SITE}/n-api/web-adapter/search?keyword={quote(keyword)}", f"suggestions for {keyword!r}",
                WWW_JSON_HEADERS, WWW_TIMEOUT, as_json=True)


# ---- seller stores (shop.coupang.com: open JSON over curl on the KR residential session,
#      the profile + catalogue as in-page calls on the store page in the box browser) ------

def fetch_store_page(seller):
    """shop.coupang.com/<vendor id | slug> -> the page HTML. An unknown
    store answers a 200 shell (NotFound)."""
    html = _get("shop", f"{SHOP}/{quote(seller)}", f"store {seller}", SHOP_PAGE_HEADERS, SHOP_TIMEOUT, as_json=False)
    if parsers.is_unknown_store(html):
        raise CoupangNotFound(f"store {seller} not found")
    return html


def fetch_store_review(store_id, vendor_id, url_name):
    """getStoreReview as an in-page fetch on the store's own page (box)."""
    params = {"storeId": store_id, "vendorId": vendor_id, "urlName": url_name or vendor_id}
    return box_json(refs.store_link(url_name or vendor_id), f"{SHOP}/api/v1/store/getStoreReview?{urlencode(params)}",
                    f"store {vendor_id} profile")


def fetch_store_follow(store_id):
    return _get("shop", f"{SHOP}/api/v1/sub/getStoreFollowInfo?storeId={store_id}", f"store {store_id} followers",
                SHOP_JSON_HEADERS, SHOP_TIMEOUT, as_json=True)


def fetch_store_top_selling(store_id, vendor_id):
    body = {"storeId": int(store_id), "vendorId": vendor_id, "topSellingPeriodType": "oneWeek", "source": "direct",
            "brandId": 0, "enableAdultItemDisplay": True}
    return _post_json("shop", f"{SHOP}/api/v2/store/top_selling", body, f"store {vendor_id} top selling",
                      SHOP_JSON_HEADERS, SHOP_TIMEOUT)


def fetch_store_listing(store_id, vendor_id, page=1, sort_key=None, category_id=None, url_name=None):
    """api/v1/listing as an in-page POST on the store's own page (box) ->
    one catalogue page (20 cards; nextPageKey is the zero-based page). An
    unknown SORT_KEY is refused with the 403 page."""
    filters = "SORT_KEY:" + (sort_key or "")
    if category_id:
        filters += f"|CATEGORY:{category_id}"
    body = {"storeId": int(store_id), "brandId": 0, "vendorId": vendor_id, "source": "direct",
            "enableAdultItemDisplay": True, "nextPageKey": max(int(page) - 1, 0), "filter": filters}
    payload = box_json(refs.store_link(url_name or vendor_id), f"{SHOP}/api/v1/listing",
                       f"store {vendor_id} products p{page}", method="POST", body=json.dumps(body))
    if isinstance(payload, dict) and payload.get("code") not in (None, 200):
        raise CoupangUpstreamError(f"store {vendor_id} products p{page}: shop answered code {payload.get('code')} {payload.get('msg')!r}")
    return payload


def fetch_store_main_category(vendor_id):
    return _post_json("shop", f"{SHOP}/api/v1/main_category", {"vendorId": vendor_id, "brandId": 0, "categoryLevel": 3},
                      f"store {vendor_id} categories", SHOP_JSON_HEADERS, SHOP_TIMEOUT)


def fetch_store_filter(vendor_id):
    return _post_json("shop", f"{SHOP}/api/v1/filter", {"filterQuery": f"VENDOR_ID:{vendor_id}", "brandId": 0},
                      f"store {vendor_id} filters", SHOP_JSON_HEADERS, SHOP_TIMEOUT)


# ---- the browser box (walled www surfaces) -------------------------------------------
# The box keeps one browser per proxy URL; the SAME URL must reach every
# call that should land on that browser (browser_client.ExitPool), and a
# refusal (403 / challenge page inside the browser) rotates the exit.

_EXITS = browser_client.ExitPool(BOX_SITE, config.coupang_browser_proxy, size=lambda: config.COUPANG_BROWSER_SLOTS)


def _box_call(label, refused=None, **kw):
    """A box fetch on whichever sticky exit's browser the box finds free
    (every exit is offered: ExitPool.fetch_any), rotating the one it used on
    a refusal (up to COUPANG_BOX_ATTEMPTS); a box outage is retryable upstream.
    `refused(res) -> message | None` names a refusal the recipe cannot see
    (a 200 whose body is a per-exit soft block): that exit is rotated too."""
    last = None
    for _ in range(max(1, int(config.COUPANG_BOX_ATTEMPTS))):
        try:
            proxy, res = _EXITS.fetch_any(BOX_SITE, **kw)
        except browser_client.BoxRefused as e:
            if e.candidate is not None:
                _EXITS.rotate(e.proxy)
            last = CoupangBlocked(f"{label}: Coupang refused the exit in the box browser: {e}")
            continue
        except browser_client.BoxUnavailable as e:
            raise CoupangUpstreamError(f"{label}: browser box unavailable: {e}")
        message = refused(res) if refused else None
        if not message:
            return res
        _EXITS.rotate(proxy)
        last = CoupangBlocked(f"{label}: Coupang refused this exit ({message})")
    raise last


def _box_status(res, label):
    status = int(res.get("status") or 0)
    body = res.get("body") or ""
    if status in (403, 429) or parsers.is_blocked(body):
        raise CoupangBlocked(f"HTTP {status} inside the box browser on {label}")
    if status == 404:
        raise CoupangNotFound(f"{label} not found")
    if status == 400:
        raise CoupangBadRequest(f"Coupang rejected {label}")
    if status >= 500 or status == 0:
        raise CoupangUpstreamError(f"HTTP {status} inside the box browser on {label}")
    if status != 200:
        raise CoupangUpstreamError(f"HTTP {status} inside the box browser on {label}: {body[:120]!r}")
    return body, res.get("final_url") or ""


def box_page(url, label):
    """One www.coupang.com page loaded as a top-level navigation -> HTML."""
    res = _box_call(label, url=url, method="GET", headers=dict(BOX_PAGE_HEADERS))
    body, _ = _box_status(res, label)
    if not parsers.rsc_payload(body):
        raise CoupangUpstreamError(f"{label}: page carried no data (title {parsers.page_title(body)!r})")
    return body


def box_json(page_url, url, label, refused=None, method="GET", body=None):
    """One JSON call run as an in-page fetch() on `page_url` (the recipe
    navigates there first when the browser is elsewhere) -> parsed JSON.
    `refused(payload) -> message | None` flags a 200 JSON that is a per-exit
    soft block, so _box_call rotates that exit. `body` (a JSON string) makes
    it a POST with a JSON content type."""
    def body_refused(res):
        try:
            return refused(json.loads(res.get("body") or ""))
        except ValueError:
            return None
    headers = {**BOX_JSON_HEADERS, PAGE_HEADER: page_url}
    if method != "GET":
        headers["content-type"] = "application/json"
    res = _box_call(label, refused=body_refused if refused else None, url=url, method=method, headers=headers, body=body)
    body, _ = _box_status(res, label)
    try:
        return json.loads(body)
    except ValueError:
        raise CoupangUpstreamError(f"non-JSON answer inside the box browser on {label}: {body[:120]!r}")


def listing_query(sort=None, min_price=None, max_price=None, rocket_only=False, page=None, list_size=None):
    params = {}
    if page and page > 1:
        params["page"] = int(page)
    if list_size:
        params["listSize"] = int(list_size)
    if sort and sort != "scoreDesc":
        params["sorter"] = sort
    if min_price is not None or max_price is not None:
        params["minPrice"] = int(min_price) if min_price is not None else ""
        params["maxPrice"] = int(max_price) if max_price is not None else ""
        params["isPriceRange"] = "true"
    if rocket_only:
        params["rocketAll"] = "true"
    return params


def fetch_search_page(query, sort=None, min_price=None, max_price=None, rocket_only=False):
    """/np/search?q= -> the page HTML (page 1 only: the site serves an
    anonymous visitor nothing past the first 60 results)."""
    params = {"q": query, "channel": "user", **listing_query(sort, min_price, max_price, rocket_only)}
    return box_page(f"{SITE}/np/search?{urlencode(params)}", f"search {query!r}")


def fetch_category_page(category_id, page=1, sort=None, min_price=None, max_price=None, rocket_only=False,
                        list_size=refs.CATEGORY_PAGE_SIZE):
    """/np/categories/<id> -> the page HTML."""
    params = listing_query(sort, min_price, max_price, rocket_only, page=page,
                           list_size=list_size if list_size != refs.CATEGORY_PAGE_SIZE else None)
    url = f"{SITE}/np/categories/{category_id}" + (f"?{urlencode(params)}" if params else "")
    return box_page(url, f"category {category_id} p{page}")


def fetch_product_page(product_id, item_id=None, vendor_item_id=None):
    """/vp/products/<id>[?itemId=&vendorItemId=] -> the page HTML. An
    unknown id answers a 200 titled "null - | 쿠팡" (NotFound)."""
    url = refs.product_link(product_id, item_id, vendor_item_id)
    html = box_page(url, f"product {product_id}")
    if parsers.is_unknown_product(html):
        raise CoupangNotFound(f"product {product_id} not found")
    return html


def fetch_reviews(product_id, item_id=None, vendor_item_id=None, page=1, sort_key="ORDER_SCORE_ASC", rating=None):
    """next-api/review on the product's own page -> the JSON (10 a page).
    The review service refuses some exits (RET9999): Blocked, so the
    retry rotates the exit."""
    params = {"productId": product_id, "page": int(page), "size": refs.REVIEW_PAGE_SIZE, "sortBy": sort_key,
              "ratingSummary": "true", "ratings": int(rating) if rating else "", "market": ""}
    payload = box_json(refs.product_link(product_id, item_id, vendor_item_id), f"{SITE}/next-api/review?{urlencode(params)}",
                       f"reviews of {product_id} p{page}", refused=parsers.review_refusal)
    refusal = parsers.review_refusal(payload)
    if refusal:
        raise CoupangBlocked(f"reviews of {product_id}: Coupang's review service refused this exit ({refusal})")
    return payload


def fetch_questions(product_id, item_id=None, vendor_item_id=None, page=1):
    """next-api/products/inquiries on the product's own page -> the JSON (15 a page)."""
    params = {"productId": product_id, "pageNo": int(page), "isPreview": "false"}
    return box_json(refs.product_link(product_id, item_id, vendor_item_id),
                    f"{SITE}/next-api/products/inquiries?{urlencode(params)}", f"questions of {product_id} p{page}")


def fetch_other_sellers(product_id, item_id, vendor_item_id):
    """next-api/products/other-seller-info on the product's own page -> the JSON."""
    params = {"productId": product_id, "selectedId": vendor_item_id, "itemId": item_id}
    return box_json(refs.product_link(product_id, item_id, vendor_item_id),
                    f"{SITE}/next-api/products/other-seller-info?{urlencode(params)}", f"other sellers of {product_id}")


if __name__ == "__main__":
    # Smoke test: the open curl surfaces, then the box (BROWSER_BOX_URLS).
    started = time.monotonic()
    best = fetch_best100("178155", "bestseller", 1)
    print(f"best100 ({time.monotonic() - started:.1f}s): {len(best.get('products', []))} cards")
    started = time.monotonic()
    page = fetch_store_page("A00996727")
    print(f"store page ({time.monotonic() - started:.1f}s): {parsers.parse_store_page(page)}")
    started = time.monotonic()
    html = fetch_search_page("무선 마우스")
    print(f"search ({time.monotonic() - started:.1f}s): {parsers.parse_search(html)['count']} cards")
    started = time.monotonic()
    html = fetch_product_page("6982437348", "18729357282", "85861963518")
    print(f"product ({time.monotonic() - started:.1f}s): {parsers.parse_product(html)['title']}")
