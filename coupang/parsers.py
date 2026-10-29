"""coupang.com payloads -> clean dicts. Pure functions, no I/O.

Inputs (coupang/fixtures, captured 2026-10-23/28: www pages through a headed
Chrome on a Korean residential exit, shop.coupang.com and the open n-api
JSON from the GKE pod):
  * www.coupang.com Next.js pages (search /np/search, category listings
    /np/categories/<id>, product /vp/products/<id>, /np/todayopen): the
    React Server Components payload in `self.__next_f.push([1,"..."])`
    chunks (rsc_payload). A search / category page carries one
    `{"searchId", "products": [card...]}` object (60 cards), a filter
    object (brands, sorters, sub-categories, attribute filters), and the
    related keywords; a product page carries `{"atfData", "staticData",
    "btfData"}` (title, option matrix with every option's vendor item,
    the selected option's price / delivery / stock, seller, policies,
    legal notice table, certifications) plus two JSON-LD blocks.
  * n-api/best100/products, n-api/homeunit/BEST_CATEGORY,
    n-api/web-adapter/category-list and the autocomplete JSON.
  * next-api/review (reviews, 10 a page, with the per-star summary),
    next-api/products/inquiries (Q&A, 15 a page), other-seller-info and
    quantity-info JSON fetched on the product page.
  * shop.coupang.com store pages (Nuxt state packed as a function call,
    read with nuxt_values) and its JSON (getStoreReview, follow info,
    top_selling, listing, main_category, filter).

Product cards share one shape across every listing (search, category,
best100, today's new, home best-by-category, store listing / top selling)
with small differences per surface; parse_card handles all of them.

Key naming: snake_case, `link` for URLs, booleans as questions, prices as
numbers + `currency`, dates ISO, null for absent values. Nothing here
raises on a partial payload."""
import html as html_lib
import json
import re
from datetime import datetime, timedelta, timezone

from coupang import refs

CURRENCY = "KRW"
THUMBNAIL_PREFIX = "https://thumbnail.coupangcdn.com/thumbnails/remote/320x320ex/image/"
TRACKING_PARAMS = ("channel", "from", "traid", "trcid", "sourceType", "subSourceType", "adType", "eventId", "searchId",
                   "src", "spec", "lptag", "wPcid", "redirect", "clickEventId", "korePlacement", "koreSubPlacement", "rank",
                   "searchRank", "itemsCount", "pvId", "trAid", "trCid")
KST = timezone(timedelta(hours=9))

_DEC = json.JSONDecoder()
_RSC_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_LD_RE = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_META_RE = {
    "og:title": re.compile(r'property="og:title"\s+content="([^"]*)"'),
    "description": re.compile(r'name="description"\s+content="([^"]*)"'),
    "og:url": re.compile(r'property="og:url"\s+content="([^"]*)"'),
}
_NUM_RE = re.compile(r"-?[0-9][0-9,]*(?:\.[0-9]+)?")
_PRODUCT_LINK_RE = re.compile(r"/v[pm]/products/([0-9]+)")

CHALLENGE_MARKERS = ("sec-if-cpt-container", "sec-bc-tile-container", "Powered and protected by")
ACCESS_DENIED_MARKERS = ("<TITLE>Access Denied</TITLE>", "errors.edgesuite.net")
COUPANG_403_MARKERS = ("요청하신 페이지의 사용권한이 없습니다", "사용권한이 제한된 페이지입니다")


# ---- scalar helpers ---------------------------------------------------------------

def _num(value):
    """"12,820" / "12820" / 12820 / {"amount": "12820"} -> 12820 (int when
    whole), None when absent or unparsable."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else value
    if isinstance(value, dict):
        for key in ("amount", "units", "price", "value"):
            if value.get(key) not in (None, ""):
                return _num(value.get(key))
        return None
    match = _NUM_RE.search(str(value))
    if not match:
        return None
    text = match.group(0).replace(",", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _int(value):
    number = _num(value)
    return int(number) if isinstance(number, (int, float)) else None


def _text(value):
    """Strip tags + entities, collapse whitespace; None when empty."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str):
        return None
    text = html_lib.unescape(_TAG_RE.sub(" ", value))
    text = " ".join(text.split())
    return text or None


def _contents_text(area, key="contents"):
    """{"contents": [{"text": "내일(일) "}, {"text": "도착"}]} -> "내일(일) 도착"."""
    if not isinstance(area, dict):
        return None
    parts = [p.get("text") for p in (area.get(key) or []) if isinstance(p, dict) and p.get("text")]
    return _text("".join(parts)) if parts else None


def _link(url):
    """Protocol-relative and bare paths -> absolute https links."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return refs.SITE + url
    if url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url


def clean_link(url):
    """An absolute link with the site's tracking parameters removed."""
    url = _link(url)
    if not url or "?" not in url:
        return url
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False) if k not in TRACKING_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def _ms_iso(value):
    """Epoch milliseconds -> ISO 8601 in Korea's zone (the site's clock)."""
    number = _num(value)
    if number is None:
        return None
    try:
        return datetime.fromtimestamp(number / 1000, tz=KST).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def _compact_iso(value):
    """"20261021142150" -> "2026-10-21T14:21:50+09:00"; "20261028" -> "2026-10-28"."""
    if not value or not isinstance(value, str) or not value.isdigit():
        return None
    try:
        if len(value) == 14:
            return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=KST).isoformat()
        if len(value) == 8:
            return datetime.strptime(value, "%Y%m%d").date().isoformat()
    except ValueError:
        return None
    return None


def _ids_from_link(link):
    """"/vp/products/123?itemId=4&vendorItemId=5" -> (123, 4, 5) as strings/None."""
    if not link or not isinstance(link, str):
        return None, None, None
    match = _PRODUCT_LINK_RE.search(link)
    product_id = match.group(1) if match else None
    item = re.search(r"[?&]itemId=([0-9]+)", link)
    vendor = re.search(r"[?&]vendorItemId=([0-9]+)", link)
    return product_id, (item.group(1) if item else None), (vendor.group(1) if vendor else None)


# ---- page helpers -----------------------------------------------------------------

def rsc_payload(page_html):
    """The Next.js RSC payload of a www.coupang.com page: every
    self.__next_f.push([1, "..."]) chunk decoded and joined. "" for a page
    without one (a block page, an error shell)."""
    if not page_html:
        return ""
    parts = []
    for chunk in _RSC_RE.findall(page_html):
        try:
            parts.append(json.loads('"' + chunk + '"'))
        except ValueError:
            continue
    return "".join(parts)


def decode_at(text, index):
    """The JSON value starting at `index`, or None."""
    if text is None or index is None or index < 0:
        return None
    try:
        value, _ = _DEC.raw_decode(text, index)
    except (ValueError, TypeError):
        return None
    return value


def find_object(text, marker, must_have=None):
    """The smallest JSON object in `text` that contains `marker` (a
    substring such as '"searchResultComponents"'): the object whose '{'
    is the nearest decodable one before the marker. `must_have` names a
    key the object must carry (else keep scanning back). None if absent."""
    if not text:
        return None
    start = text.find(marker)
    if start < 0:
        return None
    key = must_have or marker.strip('"').split('":')[0]
    pos = start
    for _ in range(2000):
        pos = text.rfind("{", 0, pos)
        if pos < 0:
            return None
        value = decode_at(text, pos)
        if isinstance(value, dict) and key in value:
            return value
    return None


def page_title(page_html):
    match = _TITLE_RE.search(page_html or "")
    return _text(match.group(1)) if match else None


def meta(page_html, name):
    match = _META_RE[name].search(page_html or "")
    return _text(match.group(1)) if match else None


def ld_json(page_html):
    """Every JSON-LD block on the page (list of dicts)."""
    out = []
    for raw in _LD_RE.findall(page_html or ""):
        try:
            value = json.loads(raw)
        except ValueError:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def is_challenge_page(text):
    head = (text or "")[:8000]
    return any(m in head for m in CHALLENGE_MARKERS)


def is_access_denied(text):
    head = (text or "")[:4000]
    return any(m in head for m in ACCESS_DENIED_MARKERS)


def is_coupang_403(text):
    """Coupang's own "no permission" page (HTTP 403, title "쿠팡!")."""
    head = (text or "")[:12000]
    return any(m in head for m in COUPANG_403_MARKERS)


def is_blocked(text):
    return is_challenge_page(text) or is_access_denied(text) or is_coupang_403(text)


# ---- product cards (every listing surface) ------------------------------------------

def _price_area(area):
    """priceArea -> {price, original_price, discount_rate, currency, ...}."""
    area = area if isinstance(area, dict) else {}
    price = (_num(area.get("i18nSalesPrice")) or _num(area.get("i18nPrice")) or _num(area.get("salesPrice"))
             or _num(area.get("price")))
    original = (_num(area.get("i18nOriginalPrice")) or _num(area.get("i18nBasePrice")) or _num(area.get("basePrice"))
                or _num(area.get("originalPrice")))
    if not original:
        original = None
    rate = _int(area.get("discountRate"))
    return {
        "price": price,
        "original_price": original if original and price and original > price else None,
        "discount_rate": rate if rate else None,
        "currency": CURRENCY,
        "discount_description": _text(area.get("instantDiscountDescription")) or _text(area.get("discountDescription")),
        "is_coupon_discount": bool(area.get("hasCouponForBtc")) or None,
    }


def _unit_price(card):
    """index.unitPrice {amount, price{units}, unit} or bundlePriceArea
    {price, cnt, unitDescription} -> {price, per, unit} (e.g. 80 KRW per
    10 g)."""
    index = card.get("index") if isinstance(card.get("index"), dict) else {}
    unit = index.get("unitPrice") if isinstance(index.get("unitPrice"), dict) else None
    if unit:
        price = _num(unit.get("price")) or _num(unit.get("priceEx")) or _num(unit.get("extendedPrice"))
        if price is not None:
            return {"price": price, "per": _num(unit.get("amount")), "unit": _text(unit.get("unit")), "currency": CURRENCY}
    bundle = card.get("bundlePriceArea") if isinstance(card.get("bundlePriceArea"), dict) else None
    if bundle and _num(bundle.get("price")) is not None:
        return {"price": _num(bundle.get("price")), "per": _num(bundle.get("cnt")),
                "unit": _text(bundle.get("unitDescription")), "currency": CURRENCY}
    return None


def _badge_ids(card):
    area = card.get("deliveryUnificationBadgeArea") if isinstance(card.get("deliveryUnificationBadgeArea"), dict) else {}
    badge = area.get("badge") if isinstance(area.get("badge"), dict) else {}
    ids = [b.get("badgeId") for b in (badge.get("badgeList") or []) if isinstance(b, dict) and b.get("badgeId")]
    return ids or None


def _cashback(card):
    area = card.get("cashBackArea") if isinstance(card.get("cashBackArea"), dict) else {}
    return _num(area.get("cashRewardText"))


def _rating(card):
    area = card.get("reviewArea") if isinstance(card.get("reviewArea"), dict) else {}
    average = area.get("ratingAverage")
    if isinstance(average, (int, float)) and not isinstance(average, bool) and average > 5:
        average = round(average / 20, 1)     # a 0-100 percentage (home / best100 cards)
    return {"rating": average if isinstance(average, (int, float)) and not isinstance(average, bool) else None,
            "reviews": _int(area.get("ratingCount"))}


def _used_offer(card):
    area = card.get("usedProductArea") if isinstance(card.get("usedProductArea"), dict) else {}
    info = area.get("usedProductInfo")
    if isinstance(info, list) and info:
        text = _text("".join(str(p.get("text", "")) for p in info if isinstance(p, dict)))
        price = _num(area.get("usedProductPrice")[0]) if isinstance(area.get("usedProductPrice"), list) and area.get("usedProductPrice") else _num(area.get("usedProductPrice"))
        return {"text": text, "price": price}
    return None


def parse_card(card):
    """One listing card (search / category / best100 / new / home / store)
    -> the product summary. None for a card without a product id."""
    if not isinstance(card, dict):
        return None
    index = card.get("index") if isinstance(card.get("index"), dict) else {}
    link = card.get("link") or card.get("detailLinkURL")
    link_pid, link_iid, link_vid = _ids_from_link(link)
    product_id = card.get("productId") or card.get("legacyProductId") or link_pid
    if not product_id:
        return None
    item_id = card.get("itemId") or index.get("itemId") or link_iid
    vendor_item_id = card.get("vendorItemId") or index.get("winnerVendorItemId") or link_vid
    title_area = card.get("imageAndTitleArea") if isinstance(card.get("imageAndTitleArea"), dict) else {}
    image = title_area.get("completeHttpUrl") or title_area.get("defaultUrl") or card.get("imageURL")
    if not image and title_area.get("oriDefaultUrl"):
        image = THUMBNAIL_PREFIX + str(title_area["oriDefaultUrl"]).lstrip("/")
    price = _price_area(card.get("priceArea"))
    rocket = card.get("rocketArea") if isinstance(card.get("rocketArea"), dict) else {}
    global_area = card.get("globalArea") if isinstance(card.get("globalArea"), dict) else {}
    sold_out = card.get("soldoutArea") if isinstance(card.get("soldoutArea"), dict) else {}
    ad = card.get("adBadgeArea") if isinstance(card.get("adBadgeArea"), dict) else {}
    deadline = card.get("deadLineArea") if isinstance(card.get("deadLineArea"), dict) else {}
    store = card.get("storeInfoArea") if isinstance(card.get("storeInfoArea"), dict) else {}
    brand = card.get("brandInfo") if isinstance(card.get("brandInfo"), dict) else {}
    return {
        "product_id": str(product_id),
        "item_id": str(item_id) if item_id else None,
        "vendor_item_id": str(vendor_item_id) if vendor_item_id else None,
        "title": _text(title_area.get("title")) or _text(index.get("title")) or _text(card.get("title")),
        "link": refs.product_link(product_id, item_id, vendor_item_id),
        "image": _link(image),
        **price,
        "unit_price": _unit_price(card),
        **_rating(card),
        "is_rocket": bool(rocket.get("show")) if rocket else None,
        "is_global": bool(global_area.get("show")) if global_area else None,
        "delivery_badges": _badge_ids(card),
        "delivery_promise": _contents_text(card.get("promisedDeliveryDateArea")),
        "shipping": _contents_text(card.get("shippingInfoArea")),
        "cashback": _cashback(card),
        "is_sold_out": bool(sold_out.get("soldout")) if sold_out else None,
        "is_almost_sold_out": bool(deadline.get("almostSoldOut")) if deadline else None,
        "is_sponsored": bool(ad.get("sponsored")) if ad else None,
        "used_offer": _used_offer(card),
        "brand": _text(brand.get("name")) if brand else None,
        "seller": _text(store.get("storeName") or store.get("name")) if store else None,
        "sales_started_at": _text(card.get("salesStartDate")),
    }


def parse_cards(cards):
    out = []
    for position, card in enumerate(cards or [], start=1):
        parsed = parse_card(card)
        if parsed:
            parsed = {"rank": position, **parsed}
            out.append(parsed)
    return out


# ---- search / category listings (www pages) ------------------------------------------

def _filter_values(items, with_count=False):
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        row = {"id": _text(item.get("value") if item.get("value") not in (None, "") else item.get("id")),
               "name": _text(item.get("name") or item.get("text"))}
        if item.get("children"):
            row["children"] = _filter_values(item.get("children"))
        out.append(row)
    return out or None


def _sub_categories(components):
    out = []
    for item in components or []:
        if not isinstance(item, dict) or not item.get("linkCode"):
            continue
        link_code = str(item.get("linkCode"))
        out.append({"id": link_code if link_code.isdigit() else None,
                    "name": _text(item.get("name")),
                    "link": _link(item.get("linkUri")) if item.get("linkUri") else None,
                    "has_children": bool(item.get("hasChild")) if "hasChild" in item else None,
                    "is_selected": bool(item.get("defaultOpen") or item.get("selected")) or None})
    return out or None


def parse_listing_filters(payload):
    """The filter object of a search / category page -> brands, offer
    conditions, attribute filters, price ranges, delivery types, sorters
    and the category tree shown beside the results."""
    obj = find_object(payload, '"searchResultComponents"')
    if not obj:
        return None
    attributes = []
    for group in obj.get("componentAttributeFilter") or []:
        if isinstance(group, dict):
            attributes.append({"id": _text(group.get("value") or group.get("id")), "name": _text(group.get("name")),
                               "values": _filter_values(group.get("children"))})
    prices = [{"id": p.get("id"), "label": _text(p.get("text")), "min_price": _num(p.get("minPrice")),
               "max_price": _num(p.get("maxPrice"))} for p in obj.get("priceRangeFilters") or []
              if isinstance(p, dict) and p.get("id") != "all"]
    delivery = []
    for item in obj.get("deliveryChargeTypeFilters") or []:
        if isinstance(item, dict):
            delivery.append({"id": _text(item.get("name")), "value": _text(item.get("value")),
                             "children": _filter_values(item.get("children"))})
    return {
        "categories": _sub_categories(obj.get("searchResultComponents")),
        "brands": _filter_values(obj.get("brands")),
        "offer_conditions": _filter_values(obj.get("offerConditions")),
        "attributes": attributes or None,
        "price_ranges": prices or None,
        "delivery_types": delivery or None,
        "sorts": [{"id": s.get("id"), "name": _text(s.get("name"))} for s in obj.get("sorters") or [] if isinstance(s, dict)] or None,
    }


def parse_related_keywords(payload):
    obj = find_object(payload, '"keywords":[{"encodedKeyword"', must_have="keywords")
    if not obj:
        return None
    words = [_text(k.get("keyword")) for k in obj.get("keywords") or [] if isinstance(k, dict)]
    return [w for w in words if w] or None


def _listing_cards(payload, marker):
    start = payload.find(marker)
    obj = decode_at(payload, start) if start >= 0 else None
    return obj if isinstance(obj, dict) and isinstance(obj.get("products"), list) else None


def parse_search(page_html):
    """A /np/search page -> {query, search_id, results, related_keywords,
    filters, is_empty}. The site answers an anonymous visitor only page 1
    (60 cards); page 2+ render "no results" (is_empty with no cards)."""
    payload = rsc_payload(page_html)
    obj = _listing_cards(payload, '{"searchId":"')
    cards = parse_cards((obj or {}).get("products"))
    meta_obj = find_object(payload, '"searchCount"')
    query = (meta_obj or {}).get("q")
    if not query:
        q_obj = find_object(payload, '"q":"', must_have="q")
        query = (q_obj or {}).get("q")
    return {
        "query": _text(query),
        "search_id": (obj or {}).get("searchId") or None,
        "is_empty": not cards,
        "count": len(cards),
        "results": cards,
        "related_keywords": parse_related_keywords(payload),
        "filters": parse_listing_filters(payload),
    }


def parse_category_page(page_html, page=1, page_size=refs.CATEGORY_PAGE_SIZE):
    """A /np/categories/<id> page -> {name, breadcrumbs, results, filters,
    pagination}. The page publishes no total, so has_next = a full page."""
    payload = rsc_payload(page_html)
    obj = _listing_cards(payload, '{"products":[{')
    cards = parse_cards((obj or {}).get("products"))
    filters = parse_listing_filters(payload)
    selected = None
    for cat in (filters or {}).get("categories") or []:
        if cat.get("is_selected"):
            selected = cat
            break
    title = page_title(page_html)
    name = title.split(" - ")[0].strip() if title and " - " in title else (selected or {}).get("name")
    return {
        "name": _text(name),
        "breadcrumbs": _breadcrumbs_from_html(page_html),
        "count": len(cards),
        "results": cards,
        "filters": filters,
        "pagination": {"page": page, "items_per_page": page_size, "has_next": len(cards) >= page_size,
                       "total_pages": None, "total_count": None},
    }


_CRUMB_RE = re.compile(r'"href":"(/np/categories/[0-9]+)","data-name":"breadcrumb","children":\["([^"]+)"')


def _breadcrumbs_from_html(page_html):
    payload = rsc_payload(page_html)
    crumbs = [{"name": _text(name), "link": _link(href), "id": href.rsplit("/", 1)[-1]}
              for href, name in _CRUMB_RE.findall(payload)]
    return crumbs or None


# ---- product page --------------------------------------------------------------------

def product_data(page_html):
    """The {"atfData", "staticData", "btfData"} object of a product page,
    or None (block page, error shell)."""
    payload = rsc_payload(page_html)
    start = payload.find('{"atfData":')
    obj = decode_at(payload, start) if start >= 0 else None
    return obj if isinstance(obj, dict) and isinstance(obj.get("atfData"), dict) else None


def has_below_fold(page_html):
    """A page opened by bare product id streams btfData (seller, policies,
    essentials, description) lazily — the payload carries "$undefined" in
    its place. Only a link with itemId + vendorItemId renders it."""
    data = product_data(page_html) or {}
    return isinstance(data.get("btfData"), dict) and bool(data["btfData"])


def is_unknown_product(page_html):
    """An unknown product id answers HTTP 200 with the title "null -  | 쿠팡"
    and an atfData without productId."""
    title = page_title(page_html) or ""
    if title.startswith("null -") or title.startswith("null |"):
        return True
    data = product_data(page_html)
    atf = (data or {}).get("atfData") if isinstance((data or {}).get("atfData"), dict) else {}
    return bool(data) and not (atf.get("productId") and (atf.get("title") or atf.get("pureTitle")))


def _quantity_price(qb):
    """quantityBase[0] (the same shape as the quantity-info JSON) -> the
    selected option's price / shipping / delivery / cashback."""
    qb = qb if isinstance(qb, dict) else {}
    price = qb.get("price") if isinstance(qb.get("price"), dict) else {}
    shipping = qb.get("shippingFee") if isinstance(qb.get("shippingFee"), dict) else {}
    delivery = qb.get("delivery") if isinstance(qb.get("delivery"), dict) else {}
    cash = qb.get("cashBackSummary") if isinstance(qb.get("cashBackSummary"), dict) else {}
    tiers = []
    for row in qb.get("priceList") or []:
        if isinstance(row, dict) and (_num(row.get("i18nPriceAmount")) is not None or _num(row.get("priceAmount")) is not None):
            tiers.append({"type": row.get("type"), "label": _text(row.get("title")),
                          "price": _num(row.get("i18nPriceAmount")) if _num(row.get("i18nPriceAmount")) is not None else _num(row.get("priceAmount"))})
    arrival = None
    for module in qb.get("moduleData") or []:
        if isinstance(module, dict) and module.get("viewType") == "PRODUCT_DETAIL_DELIVERY_INFO":
            for pdd in module.get("pddList") or []:
                if isinstance(pdd, dict):
                    arrival = {"date": _ms_iso(pdd.get("arrivalDate")), "message": _text(pdd.get("arrivalMessage")),
                               "note": _text(pdd.get("arrivalMessagePostfix")), "delivery_type": pdd.get("deliveryType"),
                               "charge_type": pdd.get("deliveryChargeType")}
                    break
            break
    sale = _num(price.get("i18nSalePrice")) if _num(price.get("i18nSalePrice")) is not None else _num(price.get("salePrice"))
    final = _num(price.get("finalPrice")) if _num(price.get("finalPrice")) is not None else _num(price.get("i18nCouponPrice"))
    return {
        "price": {
            "price": final if final is not None else sale,
            "sale_price": sale,
            "coupon_price": _num(price.get("i18nCouponPrice")) if _num(price.get("i18nCouponPrice")) is not None else _num(price.get("couponPrice")),
            "original_price": _num(price.get("i18nOriginPrice")) if _num(price.get("i18nOriginPrice")) is not None else _num(price.get("originPrice")),
            "discount_rate": _int(price.get("discountRate")),
            "unit_price": _text(price.get("saleUnitPrice")) or _text(price.get("couponUnitPrice")),
            "currency": CURRENCY,
            "has_coupon_discount": bool(price.get("hasNormalCouponDiscount") or price.get("hasWowCouponDiscount")) or None,
            "has_instant_discount": bool(price.get("hasNormalInstantDiscount") or price.get("hasWowInstantDiscount")) or None,
            "tiers": tiers or None,
            "cashback": _num(cash.get("finalCashBackAmt")),
        },
        "shipping": {
            "type": shipping.get("shippingFeeType"),
            "fee": _num(shipping.get("shippingFee")) if shipping else None,
            "original_fee": _num(shipping.get("originalShippingFee")) if shipping else None,
            "message": _text(shipping.get("message")),
            "free_condition": _text(shipping.get("freeShippingConditionMessage")),
            "currency": CURRENCY,
        } if shipping else None,
        "delivery": {
            "type": delivery.get("type"),
            "speed": delivery.get("speedType"),
            "message": _text(delivery.get("descriptions")),
            "company": _text(delivery.get("companyLabel") or delivery.get("company")),
            "arrival": arrival,
        } if delivery or arrival else None,
    }


def _option_names(option_rows):
    """valueId -> option name for every attribute of every option row."""
    names = {}
    for row in option_rows or []:
        if not isinstance(row, dict):
            continue
        for attr in row.get("attributes") or []:
            if isinstance(attr, dict) and attr.get("valueId"):
                names[str(attr["valueId"])] = _text(attr.get("name"))
    return names


def _images(entries):
    out = []
    for image in entries or []:
        if isinstance(image, dict):
            url = _link(image.get("detailImage") or image.get("origin"))
            if url:
                out.append(url)
    return out or None


def _variants(atf, names):
    """attributeVendorItemMap -> one row per purchasable option."""
    out = []
    for value_id, entry in ((atf.get("options") or {}).get("attributeVendorItemMap") or {}).items():
        if not isinstance(entry, dict) or not entry.get("vendorItemId"):
            continue
        qb = (entry.get("quantityBase") or [None])[0]
        priced = _quantity_price(qb) if isinstance(qb, dict) else None
        out.append({
            "value_id": value_id,
            "name": names.get(str(value_id)) or _text(entry.get("attributeTitle")),
            "item_id": str(entry.get("itemId")) if entry.get("itemId") else None,
            "vendor_item_id": str(entry.get("vendorItemId")),
            "item_name": _text(entry.get("itemName")),
            "link": refs.product_link(atf.get("productId"), entry.get("itemId"), entry.get("vendorItemId")),
            "price": (priced or {}).get("price", {}).get("price") if priced else None,
            "original_price": (priced or {}).get("price", {}).get("original_price") if priced else None,
            "currency": CURRENCY,
            "is_sold_out": bool(entry.get("soldOut")),
            "is_almost_sold_out": bool(entry.get("almostSoldOut")) or None,
            "buyable_quantity": _int(entry.get("buyableQuantity")),
            "is_used": bool(entry.get("used")) or None,
            "image": (_images(entry.get("images")) or [None])[0],
            "is_selected": None,
        })
    return out


def _seller(btf):
    info = ((btf.get("returnPolicyVo") or {}).get("sellerDetailInfo")) if isinstance(btf.get("returnPolicyVo"), dict) else None
    info = info if isinstance(info, dict) else {}
    address = _text(info.get("repAddress")) or _text(" ".join(p for p in (info.get("repAddress1"), info.get("repAddress2")) if p))
    return {
        "name": _text(info.get("vendorName")),
        "is_coupang_retail": bool(info.get("retail")),
        "is_marketplace": bool(info.get("threePM") or info.get("threePC")) or None,
        "representative": _text(info.get("repPersonName")),
        "phone": _text(info.get("repPhoneNum")),
        "email": _text(info.get("repEmail")),
        "address": address,
        "business_number": _text(info.get("bizNum")),
        "ecommerce_report_number": _text(info.get("ecommReportNum")),
        "customer_service_phone": _text(info.get("customerServiceNumber")),
        "country": info.get("countryCode"),
    }


def _policies(btf):
    policy = btf.get("returnPolicyVo") if isinstance(btf.get("returnPolicyVo"), dict) else {}
    delivery = policy.get("vendorItemDeliveryNotice") if isinstance(policy.get("vendorItemDeliveryNotice"), dict) else {}
    returns = policy.get("vendorItemReturnNotice") if isinstance(policy.get("vendorItemReturnNotice"), dict) else {}
    return {
        "delivery_method": _text(delivery.get("deliveryMethod")),
        "delivery_company": _text(delivery.get("deliveryCompany")),
        "delivery_charge": _text(delivery.get("deliveryCharge")),
        "shipping_period": _text(delivery.get("shippingPeriod")),
        "is_bundle_shipping": (delivery.get("batchShipment") == "가능") if delivery.get("batchShipment") else None,
        "is_rocket_install": bool(delivery.get("rocketInstall")) or None,
        "return_charge": _text(returns.get("returnCharge")),
    } if (delivery or returns) else None


def _certifications(btf):
    out = []
    for cert in btf.get("vendorItemCertifications") or []:
        if isinstance(cert, dict):
            out.append({"name": _text(cert.get("name")), "number": _text(cert.get("certificationNo")),
                        "description": _text(cert.get("description")), "link": _link(cert.get("popupUrl"))})
    return out or None


def _description_images(btf):
    out = []
    for block in btf.get("details") or []:
        if not isinstance(block, dict):
            continue
        for item in block.get("vendorItemContentDescriptions") or []:
            if isinstance(item, dict) and item.get("imageType") and item.get("content"):
                out.append(_link(item["content"]))
    return out or None


def _description_text(btf):
    parts = []
    for block in btf.get("details") or []:
        if not isinstance(block, dict):
            continue
        for item in block.get("vendorItemContentDescriptions") or []:
            if isinstance(item, dict) and not item.get("imageType") and item.get("content"):
                parts.append(_text(item["content"]))
    return "\n".join(p for p in parts if p) or None


def parse_product(page_html):
    """A /vp/products/<id> page -> the full product record. None when the
    page carries no product data (callers decide between unknown and
    blocked first)."""
    data = product_data(page_html)
    if not data:
        return None
    atf = data.get("atfData") if isinstance(data.get("atfData"), dict) else {}
    btf = data.get("btfData") if isinstance(data.get("btfData"), dict) else {}
    static = data.get("staticData") if isinstance(data.get("staticData"), dict) else {}
    product_id = atf.get("productId")
    # an unknown id still echoes the requested id, with no title and no options
    if not product_id or not (atf.get("title") or atf.get("pureTitle")):
        return None
    names = _option_names((atf.get("options") or {}).get("optionRows"))
    variants = _variants(atf, names)
    # btfData names the option the link selected; a bare-id page has no btfData,
    # and atfData then names the site's default option
    selected_vid = str(btf.get("vendorItemId") or atf.get("vendorItemId") or "") or None
    selected_iid = btf.get("itemId") or atf.get("itemId")
    selected = None
    for variant in variants:
        variant["is_selected"] = variant["vendor_item_id"] == selected_vid
        if variant["is_selected"]:
            selected = variant
    entry = None
    for value in ((atf.get("options") or {}).get("attributeVendorItemMap") or {}).values():
        if isinstance(value, dict) and str(value.get("vendorItemId") or "") == selected_vid:
            entry = value
            break
    entry = entry or {}
    quantity_base = entry.get("quantityBase") or atf.get("quantityBase")
    priced = _quantity_price(quantity_base[0]) if isinstance(quantity_base, list) and quantity_base else {}
    ld_product = next((b for b in ld_json(page_html) if b.get("@type") == "Product"), {})
    ld_crumbs = next((b for b in ld_json(page_html) if b.get("@type") == "BreadcrumbList"), {})
    breadcrumbs = [{"name": _text(c.get("name")), "link": _link(c.get("item")),
                    "id": (c.get("item") or "").rsplit("/", 1)[-1] if "/np/categories/" in (c.get("item") or "") else None}
                   for c in ld_crumbs.get("itemListElement") or [] if isinstance(c, dict)]
    breadcrumbs = [c for c in breadcrumbs if c["name"] and c["name"] != "쿠팡 홈"] or None
    leaf = atf.get("leafCategoryInfo") if isinstance(atf.get("leafCategoryInfo"), dict) else {}
    rating_ld = ld_product.get("aggregateRating") if isinstance(ld_product.get("aggregateRating"), dict) else {}
    offers = ld_product.get("offers") if isinstance(ld_product.get("offers"), dict) else {}
    social = None
    for module in ((quantity_base or [{}])[0] or {}).get("moduleData") or []:
        if isinstance(module, dict) and module.get("viewType") == "PRODUCT_DETAIL_SOCIAL_PROOF_NUDGE":
            social = {"recent_buyers": _int(module.get("socialProofNumUsers")), "message": _text(module.get("highlightText")),
                      "four_five_star_reviews": _int(module.get("numUsersFourFiveStarReview"))}
            break
    additional = atf.get("additionalData") if isinstance(atf.get("additionalData"), dict) else {}
    selling = atf.get("sellingInfoVo") if isinstance(atf.get("sellingInfoVo"), dict) else {}
    option_rows = [{"name": _text(r.get("name")), "type": r.get("displayType"),
                    "values": [{"value_id": a.get("valueId"), "name": _text(a.get("name")), "image": _link((a.get("image") or {}).get("url")) if isinstance(a.get("image"), dict) else _link(a.get("image"))}
                               for a in r.get("attributes") or [] if isinstance(a, dict)]}
                   for r in (atf.get("options") or {}).get("optionRows") or [] if isinstance(r, dict)]
    return {
        "product_id": str(product_id),
        "item_id": str(selected_iid) if selected_iid else (selected or {}).get("item_id"),
        "vendor_item_id": selected_vid,
        "title": _text(atf.get("title")) or _text(ld_product.get("name")),
        "short_title": _text(atf.get("pureTitle")),
        "option_title": _text(atf.get("attributeTitle")),
        "brand": _text(atf.get("brand")) or (_text(additional.get("officialBrandName")) if additional else None),
        "link": refs.product_link(product_id, selected_iid, selected_vid),
        "images": _images(entry.get("images")) or _images(atf.get("images"))
                  or ([_link(i) for i in ld_product.get("image")] if isinstance(ld_product.get("image"), list) else None),
        **(priced or {"price": None, "shipping": None, "delivery": None}),
        "availability": {
            "is_sold_out": bool(entry.get("soldOut")) if entry else None,
            "is_almost_sold_out": bool(entry.get("almostSoldOut")) or None,
            "buyable_quantity": _int(entry.get("buyableQuantity")),
            "is_in_stock": (offers.get("availability") or "").endswith("InStock") if offers.get("availability") else None,
            "is_restock_notification_only": bool(entry.get("restockNotification")) or None,
        },
        "rating": _num(rating_ld.get("ratingValue")) if rating_ld else (round(_num(atf.get("ratingAveragePercentage")) / 20, 1) if _num(atf.get("ratingAveragePercentage")) else None),
        "reviews": _int(atf.get("ratingCount")) if _int(atf.get("ratingCount")) is not None else _int(rating_ld.get("ratingCount")),
        "social_proof": social,
        "delivery_type": additional.get("deliveryType") if additional else None,
        "is_rocket": (additional.get("deliveryType") or "").startswith("ROCKET") if additional.get("deliveryType") else None,
        "expiration_date": _text(additional.get("expirationDate")) if additional else None,
        "country_of_origin": _text(selling.get("countryOfOrigin")) or _text(atf.get("countryOfOrigin")),
        "selling_info": [_text(s) for s in selling.get("sellingInfo") or [] if _text(s)] or None,
        "category": {"id": str(leaf.get("categoryId")) if leaf.get("categoryId") else None, "name": _text(leaf.get("name")),
                     "path": [_text(p) for p in reversed(leaf.get("parentsCategoryNames") or []) if _text(p) and p not in ("HOME", "KAN")] or None} if leaf else None,
        "breadcrumbs": breadcrumbs,
        "options": option_rows or None,
        "variants": variants or None,
        "other_seller_count": _int(entry.get("otherSellerCount")) if _int(entry.get("otherSellerCount")) is not None else _int(atf.get("otherSellerCount")),
        "seller": _seller(btf),
        "policies": _policies(btf),
        "essentials": [{"title": _text(e.get("title")), "value": _text(e.get("description"))}
                       for e in btf.get("essentials") or [] if isinstance(e, dict)] or None,
        "certifications": _certifications(btf),
        "selling_points": [_text(p) for p in btf.get("productSellingPoints") or [] if _text(p)] or None,
        "description": _description_text(btf),
        "description_images": _description_images(btf),
        "is_adult": bool(atf.get("adult")) or None,
        "has_brand_shop": bool(atf.get("hasBrandShop")) or None,
    }


# ---- product page JSON (reviews, questions, other sellers, quantity info) --------------

def review_refusal(payload):
    """next-api/review answered RET9999 ("the review system is unstable")
    -> the message; the site soft-blocks review TEXT per exit. None when
    the answer is a normal one."""
    if isinstance(payload, dict) and payload.get("rCode") not in (None, "RET0000"):
        return _text(payload.get("rMessage")) or payload.get("rCode")
    return None


def _review(item):
    item = item if isinstance(item, dict) else {}
    member = item.get("member") if isinstance(item.get("member"), dict) else {}
    images = [_link(a.get("imgSrcOrigin") or a.get("imgSrcThumbnail")) for a in item.get("attachments") or [] if isinstance(a, dict)]
    videos = [_link(v.get("videoUrl") or v.get("url") or v.get("src")) for v in item.get("videoAttachments") or [] if isinstance(v, dict)]
    survey = [{"question": _text(a.get("question")), "answer": _text(a.get("answer"))}
              for a in item.get("reviewSurveyAnswers") or [] if isinstance(a, dict) and _text(a.get("answer"))]
    vendor = _text(item.get("vendorName"))
    if vendor and vendor.startswith("판매자:"):
        vendor = _text(vendor.split(":", 1)[1])
    return {
        "id": str(item.get("reviewId")) if item.get("reviewId") else None,
        "rating": _int(item.get("rating")),
        "title": _text(item.get("title")),
        "content": item.get("content").strip() if isinstance(item.get("content"), str) and item.get("content").strip() else None,
        "created_at": _ms_iso(item.get("reviewAt") or item.get("createdAt")),
        "reviewer": {
            "name": _text(item.get("displayName") or member.get("name")),
            "label": _text(item.get("displayWriter")),
            "badges": [_text(b) for b in item.get("reviewerBadges") or [] if _text(b)] or None,
            "rank": _text(item.get("reviewerRank")),
        },
        "helpful": _int(item.get("helpfulTrueCount")) if item.get("helpfulTrueCount") is not None else _int(item.get("helpfulCount")),
        "not_helpful": _int(item.get("helpfulFalseCount")),
        "comments": _int(item.get("commentCount")),
        "images": [i for i in images if i] or None,
        "videos": [v for v in videos if v] or None,
        "survey": survey or None,
        "is_incentivized": bool(item.get("incentive")) or None,
        "item": {"item_id": str(item.get("itemId")) if item.get("itemId") else None,
                 "vendor_item_id": str(item.get("vendorItemId")) if item.get("vendorItemId") else None,
                 "name": _text(item.get("itemName")), "image": _link(item.get("itemImagePath"))},
        "seller": vendor,
    }


def parse_reviews(payload, page=1):
    """next-api/review JSON -> {summary, results, pagination}."""
    data = (payload or {}).get("rData") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    summary = data.get("ratingSummaryTotal") if isinstance(data.get("ratingSummaryTotal"), dict) else {}
    paging = data.get("paging") if isinstance(data.get("paging"), dict) else {}
    stars = {str(s.get("rating")): {"count": _int(s.get("count")), "percentage": _int(s.get("percentage"))}
             for s in summary.get("ratingSummaries") or [] if isinstance(s, dict) and s.get("rating") is not None}
    results = [_review(r) for r in paging.get("contents") or []]
    total = _int(paging.get("totalCount"))
    total_pages = _int(paging.get("totalPage"))
    return {
        "summary": {
            "rating": _num(summary.get("ratingAverage")),
            "reviews": _int(summary.get("ratingCount")) if _int(summary.get("ratingCount")) is not None else _int(data.get("reviewTotalCount")),
            "stars": stars or None,
            "has_videos": bool(data.get("videoAvailable")) or None,
        },
        "results": results,
        "pagination": {"page": _int(paging.get("currentPage")) or page, "items_per_page": _int(paging.get("sizePerPage")) or refs.REVIEW_PAGE_SIZE,
                       "total_pages": total_pages if total_pages is not None else 0, "total_count": total if total is not None else 0},
    }


def _question(item):
    item = item if isinstance(item, dict) else {}
    answers = []
    for comment in item.get("comments") or []:
        if isinstance(comment, dict):
            answers.append({"id": str(comment.get("inquiryCommentId")) if comment.get("inquiryCommentId") else None,
                            "content": comment.get("content").strip() if isinstance(comment.get("content"), str) else None,
                            "author": _text(comment.get("displayWriter")),
                            "created_at": _compact_iso(comment.get("createdAt")),
                            "is_ai_answer": bool(comment.get("isAnsweredByCoupangAi")) or None})
    return {
        "id": str(item.get("inquiryId")) if item.get("inquiryId") else None,
        "content": item.get("content").strip() if isinstance(item.get("content"), str) else None,
        "created_at": _compact_iso(item.get("createdAt")),
        "author": _text(item.get("displayWriter")),
        "option": _text(item.get("serializedAttrName")),
        "vendor_item_id": str(item.get("vendorItemId")) if item.get("vendorItemId") else None,
        "seller": {"id": _text(item.get("vendorId")), "name": _text(item.get("vendorName"))},
        "is_answered": bool(answers),
        "answers": answers or None,
    }


def parse_questions(payload, page=1):
    """next-api/products/inquiries JSON -> {results, pagination}."""
    success = (payload or {}).get("success") if isinstance(payload, dict) else None
    data = (success or {}).get("rData") if isinstance(success, dict) else None
    data = data if isinstance(data, dict) else {}
    nav = data.get("navigation") if isinstance(data.get("navigation"), dict) else {}
    results = [_question(q) for q in nav.get("contents") or []]
    total = _int(data.get("totalElements"))
    total_pages = _int(nav.get("totalPageIndex"))
    return {
        "results": results,
        "pagination": {"page": _int(nav.get("currentPageIndex")) or page, "items_per_page": refs.QUESTION_PAGE_SIZE,
                       "total_pages": total_pages if total_pages is not None else 0, "total_count": total if total is not None else 0},
    }


def parse_other_sellers(payload):
    """next-api/products/other-seller-info JSON -> [offer...]."""
    payload = payload if isinstance(payload, dict) else {}
    out = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        delivery = item.get("deliveryInfo") if isinstance(item.get("deliveryInfo"), dict) else {}
        rating = item.get("sellerStoreRating") if isinstance(item.get("sellerStoreRating"), dict) else {}
        display = rating.get("display") if isinstance(rating.get("display"), dict) else {}
        out.append({
            "vendor_item_id": str(item.get("vendorItemId")) if item.get("vendorItemId") else None,
            "seller": _text(item.get("vendorName")),
            "price": _num(item.get("i18nPrice")) if _num(item.get("i18nPrice")) is not None else _num(item.get("price")),
            "currency": CURRENCY,
            "is_selected": bool(item.get("selected")),
            "shipping": _text(delivery.get("deliveryChargePolicy") or delivery.get("shippingFeeMessage")),
            "delivery_promise": _text(delivery.get("deliverDate")),
            "seller_rating": {"score": _text(display.get("score")), "count": _int(rating.get("total"))} if rating else None,
        })
    return {"title": _text(payload.get("title")), "count": _int(payload.get("totalCount")) if payload.get("totalCount") is not None else len(out),
            "results": out}


# ---- best100 / today's new / home best-by-category (open JSON) --------------------------

def parse_best100(payload):
    """n-api/best100/products JSON -> the cards (30 a page)."""
    payload = payload if isinstance(payload, dict) else {}
    return parse_cards(payload.get("products"))


def parse_todayopen(page_html):
    """/np/todayopen -> {date, count, results, total_count}. The page
    serves one page of 48 (its own page param is ignored)."""
    payload = rsc_payload(page_html)
    start = payload.find('{"todayData":')
    obj = decode_at(payload, start) if start >= 0 else None
    data = (obj or {}).get("todayData") if isinstance(obj, dict) else None
    data = data if isinstance(data, dict) else {}
    cards = parse_cards(data.get("products"))
    return {
        "date": _compact_iso(data.get("currentDate")),
        "count": len(cards),
        "total_count": _int(data.get("productTotalCount")),
        "results": cards,
    }


def parse_home_best(payload, codes=None):
    """n-api/homeunit/BEST_CATEGORY JSON -> one block per category unit:
    its 30 best products, hot keywords and promotion banners."""
    payload = payload if isinstance(payload, dict) else {}
    out = []
    for unit in payload.get("categoryBestList") or []:
        if not isinstance(unit, dict):
            continue
        kind = unit.get("bestCategoryType") if isinstance(unit.get("bestCategoryType"), dict) else {}
        code = kind.get("name")
        if codes and code not in codes:
            continue
        keywords = []
        for kw in unit.get("keywords") or []:
            asset = ((kw or {}).get("index") or {}).get("itemAsset") if isinstance(kw, dict) else None
            if isinstance(asset, dict) and asset.get("keyword"):
                keywords.append({"keyword": _text(asset.get("keyword")), "link": clean_link(asset.get("pcLinkUrl"))})
        promotions = []
        for promo in unit.get("promotions") or []:
            asset = ((promo or {}).get("index") or {}).get("itemAsset") if isinstance(promo, dict) else None
            if isinstance(asset, dict) and (asset.get("mainTitle") or asset.get("pcLinkUrl")):
                promotions.append({"title": _text(asset.get("mainTitle")), "subtitle": _text(asset.get("subTitle")),
                                   "link": clean_link(asset.get("pcLinkUrl"))})
        out.append({
            "code": code,
            "name": _text((unit.get("title") or "").replace("\n", " ")),
            "category_id": (unit.get("linkUri") or "").rsplit("/", 1)[-1] or None,
            "link": _link(unit.get("linkUri")),
            "results": parse_cards(unit.get("products")),
            "hot_keywords": keywords or None,
            "promotions": promotions or None,
        })
    return out


def _category_node(node, depth=1, max_depth=3):
    if not isinstance(node, dict) or not node.get("linkCode"):
        return None
    link_code = str(node.get("linkCode"))
    children = None
    if depth < max_depth:
        children = [c for c in (_category_node(ch, depth + 1, max_depth) for ch in node.get("visibleChildren") or []) if c] or None
    return {"id": link_code if link_code.isdigit() else None, "name": _text(node.get("name")),
            "link": _link(node.get("linkUri")), "children": children}


def parse_category_list(payload):
    """n-api/web-adapter/category-list JSON -> the shopping category tree
    (3 levels), plus the theme / travel menus."""
    gnb = (((payload or {}).get("data") or {}).get("gnb")) if isinstance(payload, dict) else None
    gnb = gnb if isinstance(gnb, dict) else {}
    tree = lambda key: [c for c in (_category_node(n) for n in gnb.get(key) or []) if c] or None
    return {"categories": tree("shoppingComponent"), "themes": tree("themeComponent"), "travel": tree("travelComponent")}


def parse_suggestions(payload):
    """n-api/web-adapter/search?keyword= JSON -> the suggested keywords."""
    out = []
    for item in payload if isinstance(payload, list) else []:
        if isinstance(item, dict) and _text(item.get("keyword")):
            out.append(_text(item.get("keyword")))
    return out


# ---- seller stores (shop.coupang.com) ---------------------------------------------------

_NUXT_HEAD_RE = re.compile(r"window\.__NUXT__=\(function\(([^)]*)\)\{")
_NUXT_ARGS_RE = re.compile(r"\}\((.*?)\)\);?\s*</script>", re.S)


def nuxt_values(page_html, keys):
    """The store page's Nuxt state is `(function(a,b,c...){...}(arg0, arg1,
    ...))`: every scalar is a parameter name. For each key in `keys` the
    first `key:<token>` in the body is resolved: a parameter name maps to
    its argument, a literal is used as is. -> {key: value | None}."""
    out = {k: None for k in keys}
    if not page_html:
        return out
    start = page_html.find("window.__NUXT__=")
    if start < 0:
        return out
    head = _NUXT_HEAD_RE.search(page_html, start)
    if not head:
        return out
    params = [p.strip() for p in head.group(1).split(",") if p.strip()]
    tail = _NUXT_ARGS_RE.search(page_html, head.end())
    args = []
    if tail:
        raw = tail.group(1).replace("void 0", "null")
        raw = re.sub(r"(?<![0-9A-Za-z_$.])\.(\d)", r"0.\1", raw)       # JS ".9375" -> "0.9375"
        try:
            args = json.loads("[" + raw + "]")
        except ValueError:
            args = []
    body_end = tail.start() if tail else len(page_html)
    body = page_html[head.end():body_end]
    lookup = dict(zip(params, args)) if len(args) == len(params) else {}
    for key in keys:
        for match in re.finditer(r"\b" + re.escape(key) + r":([A-Za-z_$][A-Za-z0-9_$]*|\"[^\"]*\"|-?[0-9]+(?:\.[0-9]+)?)", body):
            token = match.group(1)
            value = None
            if token.startswith('"'):
                value = json.loads(token)
            elif re.match(r"^-?[0-9]", token):
                value = _num(token)
            elif token in lookup:
                value = lookup[token]
            if value not in (None, "", False):
                out[key] = value
                break
    return out


def is_unknown_store(page_html):
    """An unknown vendor id / slug answers a 200 shell: no og:title, no
    store id anywhere."""
    if not page_html:
        return True
    return meta(page_html, "og:title") is None and "storeId" not in page_html


def parse_store_page(page_html):
    """A shop.coupang.com/<vendor id | slug> page -> {store_id, vendor_id,
    name, description, link}."""
    values = nuxt_values(page_html, ("storeId", "vendorId", "urlName"))
    store_id = values.get("storeId")
    vendor_id = values.get("vendorId") if isinstance(values.get("vendorId"), str) else None
    in_links = re.search(r"vendorId=(A[0-9]{8})&(?:amp;)?storeId=([0-9]+)", page_html or "")
    if not (isinstance(store_id, (int, float, str)) and str(store_id).isdigit()):
        store_id = in_links.group(2) if in_links else None
    if not (vendor_id and refs.VENDOR_ID_RE.match(vendor_id)):
        vendor_id = in_links.group(1) if in_links else None
    title = meta(page_html, "og:title") or ""
    name = re.sub(r"^쿠팡이 추천하는\s*", "", title)
    name = re.sub(r"\s*관련 혜택과 특가$", "", name) or None
    canonical = meta(page_html, "og:url")
    return {
        "store_id": str(store_id) if store_id else None,
        "vendor_id": vendor_id,
        "slug": values.get("urlName") if isinstance(values.get("urlName"), str) else None,
        "name": _text(name),
        "description": meta(page_html, "description"),
        "link": canonical.split("?")[0] if canonical else None,
    }


def parse_store_review(payload):
    """shop.coupang.com/api/v1/store/getStoreReview -> the seller profile."""
    payload = payload if isinstance(payload, dict) else {}
    contact = payload.get("vendorContactInfo") if isinstance(payload.get("vendorContactInfo"), dict) else payload
    return {
        "name": _text(payload.get("name") or contact.get("name")),
        "rating_count": _int(payload.get("ratingCount")),
        "thumbs_up": _int(payload.get("thumbUpCount")),
        "thumbs_down": _int(payload.get("thumbDownCount")),
        "satisfaction_percent": _int(payload.get("thumbUpRatio")),
        "representative": _text(contact.get("repPersonName")),
        "phone": _text(contact.get("repPhoneNum")),
        "email": _text(contact.get("repEmail")),
        "address": _text(" ".join(p for p in (contact.get("repAddr1"), contact.get("repAddr2")) if p)),
        "business_number": _text(contact.get("businessNumber")),
        "is_quality_seller": bool(payload.get("qualitySellerBadgeDto")) or None,
    }


def parse_store_follow(payload):
    payload = payload if isinstance(payload, dict) else {}
    return _int(payload.get("followCount"))


def parse_store_listing(payload, page=1):
    """shop.coupang.com/api/v1/listing (and api/v2/store/top_selling) ->
    {results, pagination}."""
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else {}
    cards = parse_cards(data.get("products"))
    total = _int(data.get("totalCount"))
    return {
        "count": len(cards),
        "results": cards,
        "pagination": {"page": page, "items_per_page": refs.STORE_PAGE_SIZE,
                       "total_pages": -(-total // refs.STORE_PAGE_SIZE) if total else 0, "total_count": total if total is not None else 0},
    }


def parse_store_categories(main_category, filters):
    """api/v1/main_category (the store's featured categories with images)
    + api/v1/filter (every category / brand the store's products fall
    in) -> {featured, categories, brands}."""
    featured = [{"id": str(c.get("id")), "name": _text(c.get("name")), "image": _link(c.get("image"))}
                for c in ((main_category or {}).get("data") or {}).get("categories") or [] if isinstance(c, dict) and c.get("id")]
    categories, brands = None, None
    for group in ((filters or {}).get("data") or {}).get("extraFilters") or []:
        if not isinstance(group, dict):
            continue
        rows = [{"id": _text(f.get("value") or f.get("id")), "name": _text(f.get("name"))} for f in group.get("filters") or [] if isinstance(f, dict)]
        if group.get("valueType") == "CATEGORY":
            categories = rows or None
        elif group.get("valueType") == "BRAND_KEY":
            brands = rows or None
    return {"featured": featured or None, "categories": categories, "brands": brands}
