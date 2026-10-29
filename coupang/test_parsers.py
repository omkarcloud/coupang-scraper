"""Every parser against every fixture (coupang/fixtures, captured
2026-10-23/28: www pages through a headed Chrome on a Korean residential
exit, shop.coupang.com and the open n-api JSON from the GKE pod): the happy
path, the sparse / empty answers, and the not-found / blocked pages."""
import gzip
import json
import os

import pytest

from coupang import parsers, refs

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    opener = gzip.open if name.endswith(".gz") else open
    with opener(os.path.join(FX, name), "rt", encoding="utf-8") as f:
        return json.load(f) if ".json" in name else f.read()


# ---- page helpers ------------------------------------------------------------------

def test_rsc_payload_and_block_pages():
    assert parsers.rsc_payload("") == "" and parsers.rsc_payload(None) == ""
    assert '{"searchId":' in parsers.rsc_payload(load("search_wireless_mouse.html.gz"))
    assert parsers.is_coupang_403(load("coupang_403.html"))
    assert parsers.is_blocked(load("coupang_403.html"))
    assert not parsers.is_blocked(load("search_wireless_mouse.html.gz"))
    assert parsers.is_access_denied("<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>You don't have permission")
    assert parsers.is_challenge_page('<div id="sec-if-cpt-container" role="main" style="display: none">')
    assert parsers.find_object("", '"x"') is None and parsers.decode_at("{", 0) is None


def test_scalar_helpers():
    assert parsers._num("12,820") == 12820 and parsers._num({"amount": "12820"}) == 12820
    assert parsers._num("최대 1,460원 적립") == 1460 and parsers._num("") is None and parsers._num(True) is None
    assert parsers._text("<em class='x'>무료배송</em> &amp; more") == "무료배송 & more"
    assert parsers._compact_iso("20261021142150") == "2026-10-21T14:21:50+09:00"
    assert parsers._compact_iso("20261028") == "2026-10-28" and parsers._compact_iso("x") is None
    assert parsers._ms_iso(1792239577000).startswith("2026-10-")
    assert parsers.clean_link("/np/search?q=a&channel=home&searchId=1") == "https://www.coupang.com/np/search?q=a"


# ---- search ------------------------------------------------------------------------

def test_search_page_cards_keywords_and_filters():
    out = parsers.parse_search(load("search_wireless_mouse.html.gz"))
    assert out["query"] == "무선 마우스" and out["count"] == 60 and not out["is_empty"] and out["search_id"]
    first = out["results"][0]
    assert first["rank"] == 1 and first["product_id"].isdigit() and first["item_id"] and first["vendor_item_id"]
    assert first["link"].startswith("https://www.coupang.com/vp/products/") and first["image"].startswith("https://")
    assert first["currency"] == "KRW" and isinstance(first["price"], int) and first["is_sponsored"] is True
    organic = next(c for c in out["results"] if not c["is_sponsored"])
    assert organic["rating"] and organic["reviews"] > 0 and organic["is_rocket"] in (True, False)
    assert sum(1 for c in out["results"] if c["is_sponsored"]) == 10
    discounted = next(c for c in out["results"] if c["original_price"])
    assert discounted["original_price"] > discounted["price"] and discounted["discount_rate"]
    assert out["related_keywords"][:2] == ["로지텍무선마우스", "무선마우스"]
    filters = out["filters"]
    assert filters["sorts"][0] == {"id": "scoreDesc", "name": "쿠팡 랭킹순"} and len(filters["brands"]) == 20
    assert filters["categories"][0] == {"id": "178255", "name": "가전디지털", "link": "https://www.coupang.com/np/categories/178255",
                                        "has_children": None, "is_selected": None}
    assert filters["offer_conditions"][0] == {"id": "NEW", "name": "새 상품"}
    assert filters["price_ranges"][0]["max_price"] == 20000 and filters["attributes"][0]["values"]


def test_search_page_two_is_empty_not_an_error():
    out = parsers.parse_search(load("search_page2_empty.html.gz"))
    assert out["is_empty"] and out["count"] == 0 and out["results"] == [] and out["query"] == "무선 마우스"


def test_search_on_a_block_page_is_empty():
    out = parsers.parse_search(load("coupang_403.html"))
    assert out["is_empty"] and out["results"] == [] and out["filters"] is None


# ---- category listing ----------------------------------------------------------------

def test_category_page_cards_breadcrumbs_and_has_next():
    out = parsers.parse_category_page(load("category_laptops_p1.html.gz"), 1)
    assert out["name"] == "노트북" and out["count"] == 60
    assert out["breadcrumbs"] == [{"name": "가전디지털", "link": "https://www.coupang.com/np/categories/178255", "id": "178255"},
                                  {"name": "노트북", "link": "https://www.coupang.com/np/categories/497135", "id": "497135"}]
    assert out["pagination"] == {"page": 1, "items_per_page": 60, "has_next": True, "total_pages": None, "total_count": None}
    assert out["filters"]["categories"][0]["is_selected"] is True and out["filters"]["sorts"][0]["id"] == "bestAsc"
    assert all(c["product_id"] and c["title"] for c in out["results"])
    page10 = parsers.parse_category_page(load("category_laptops_p10.html.gz"), 10)
    assert page10["pagination"]["page"] == 10 and page10["count"] == 60
    assert [c["product_id"] for c in page10["results"]] != [c["product_id"] for c in out["results"]]


# ---- product page ------------------------------------------------------------------

def test_product_page_full_record():
    out = parsers.parse_product(load("product_sauce.html.gz"))
    assert out["product_id"] == "6982437348" and out["item_id"] == "18729357282" and out["vendor_item_id"] == "85861963518"
    assert out["title"] == "청수식품 우동다시 소스, 1.8L, 6개" and out["short_title"] == "청수식품 우동다시 소스"
    assert out["option_title"] == "1.8L · 6개" and out["brand"] is None
    assert out["link"] == "https://www.coupang.com/vp/products/6982437348?itemId=18729357282&vendorItemId=85861963518"
    assert len(out["images"]) == 4 and out["images"][0].startswith("https://thumbnail.coupangcdn.com/")
    assert out["price"]["price"] == 40390 and out["price"]["original_price"] == 48000 and out["price"]["discount_rate"] == 15
    assert out["price"]["unit_price"] == "100ml당 374원" and out["price"]["currency"] == "KRW" and out["price"]["cashback"] == 2020
    assert out["shipping"] == {"type": "FREE", "fee": 0, "original_fee": 2500, "message": "무료배송", "free_condition": None, "currency": "KRW"}
    assert out["delivery"]["type"] == "ROCKET_DELIVERY" and out["delivery"]["arrival"]["date"].startswith("2026-10-25")
    assert out["availability"] == {"is_sold_out": False, "is_almost_sold_out": None, "buyable_quantity": 10, "is_in_stock": True,
                                   "is_restock_notification_only": None}
    assert out["rating"] == 4.8 and out["reviews"] == 26498 and out["social_proof"]["recent_buyers"] == 743
    assert out["delivery_type"] == "ROCKET_WOW" and out["is_rocket"] is True and out["expiration_date"] == "2027-06-15"
    assert out["category"] == {"id": "1188", "name": "소스류", "path": ["식품", "장/오일/소스", "소스/드레싱/식초"]}
    assert out["breadcrumbs"][0] == {"name": "식품", "link": "https://www.coupang.com/np/categories/194276", "id": "194276"}
    assert out["options"][0]["name"] == "개당 용량 × 수량" and len(out["options"][0]["values"]) == 16
    assert len(out["variants"]) == 16
    selected = next(v for v in out["variants"] if v["is_selected"])
    assert selected["vendor_item_id"] == "85861963518" and selected["price"] == 40390 and selected["name"] == "1.8L × 6개"
    other = next(v for v in out["variants"] if not v["is_selected"])
    assert other["item_name"] and other["link"].endswith(f"vendorItemId={other['vendor_item_id']}") and other["price"] == 33660
    assert out["seller"]["is_coupang_retail"] is True and out["seller"]["name"] is None and out["seller"]["country"] == "KR"
    assert out["policies"]["delivery_method"] == "순차배송" and "반품비" in out["policies"]["return_charge"]
    assert out["essentials"][0] == {"title": "제품명", "value": "컨텐츠 참조"} and len(out["essentials"]) == 11
    assert out["selling_info"][0].startswith("소비기한") and out["description_images"] and out["certifications"] is None
    assert out["other_seller_count"] == 14


def test_product_page_with_brand_and_certifications():
    out = parsers.parse_product(load("product_airfryer.html.gz"))
    assert out["title"] == "홈플래닛 에어프라이어 2L" and out["brand"] == "홈플래닛"
    assert out["price"]["price"] == 30990 and out["price"]["original_price"] == 56300 and out["price"]["discount_rate"] == 44
    assert out["certifications"][0]["name"] == "KC인증 전기용품 안전인증" and out["certifications"][0]["number"] == "HU072155-23026B"
    assert out["category"]["name"] == "에어프라이어" and out["breadcrumbs"][-1]["name"] == "오븐형 에어프라이어"
    assert [o["name"] for o in out["options"]] == ["모델명/품번", "색상"] and len(out["variants"]) == 1


def test_unknown_product_page():
    html = load("product_unknown.html.gz")
    assert parsers.is_unknown_product(html)
    assert parsers.parse_product(html) is None
    assert not parsers.is_unknown_product(load("product_sauce.html.gz"))
    assert parsers.parse_product(load("coupang_403.html")) is None
    assert parsers.parse_product("") is None


# ---- reviews / questions / other sellers ---------------------------------------------

def test_reviews_full_page():
    out = parsers.parse_reviews(load("reviews_laptop.json"), 1)
    assert out["summary"]["rating"] == 4.5 and out["summary"]["reviews"] == 464 and out["summary"]["stars"]["5"]["count"] == 393
    assert out["pagination"] == {"page": 1, "items_per_page": 10, "total_pages": 47, "total_count": 464}
    assert len(out["results"]) == 10
    first = out["results"][0]
    assert first["id"] == "1037781554" and first["rating"] == 5 and first["content"].startswith("**고민 끝에")
    assert first["created_at"].startswith("2026-10-") and first["reviewer"]["name"] == "김*희"
    assert first["reviewer"]["label"] == "쿠팡실구매자" and first["helpful"] == 3 and first["not_helpful"] == 0
    assert first["images"][0].startswith("https://thumbnail.coupangcdn.com/") and first["videos"] is None
    assert first["survey"][0] == {"question": "사용 목적", "answer": "사무용"}
    assert first["item"]["vendor_item_id"] == "94879476086" and first["seller"] == "주식회사 진과함께"
    assert first["is_incentivized"] is None


def test_reviews_refused_and_empty():
    refused = load("reviews_refused.json")
    assert "상품평" in parsers.review_refusal(refused)
    assert parsers.review_refusal(load("reviews_laptop.json")) is None
    empty = parsers.parse_reviews(load("reviews_no_contents.json"), 1)
    assert empty["summary"]["reviews"] == 2263 and empty["results"] == []
    assert empty["pagination"] == {"page": 1, "items_per_page": 10, "total_pages": 0, "total_count": 0}
    assert parsers.parse_reviews({}, 2)["pagination"]["page"] == 2 and parsers.parse_reviews(None, 1)["results"] == []


def test_questions_pages():
    out = parsers.parse_questions(load("questions_airfryer_p1.json"), 1)
    assert out["pagination"] == {"page": 1, "items_per_page": 15, "total_pages": 24, "total_count": 94}
    first = out["results"][0]
    assert first["id"] == "162465546" and first["created_at"] == "2026-10-21T14:21:50+09:00" and first["option"] == "AF-201-1 | 블랙"
    assert first["seller"] == {"id": "A00010028", "name": "쿠팡"} and first["is_answered"] and len(first["answers"]) == 2
    assert first["answers"][0]["author"] == "[COUPANG]" and first["answers"][0]["created_at"] == "2026-10-21T15:19:39+09:00"
    page2 = parsers.parse_questions(load("questions_sauce_p2.json"), 2)
    assert page2["pagination"]["page"] == 2 and page2["pagination"]["total_count"] == 82 and len(page2["results"]) == 15
    assert parsers.parse_questions({}, 3)["pagination"] == {"page": 3, "items_per_page": 15, "total_pages": 0, "total_count": 0}


def test_other_sellers():
    out = parsers.parse_other_sellers(load("other_sellers_sauce.json"))
    assert out["count"] == 14 and out["title"].startswith("청수식품")
    selected = next(s for s in out["results"] if s["is_selected"])
    assert selected["seller"] == "쿠팡" and selected["price"] == 40390
    other = out["results"][1]
    assert other["seller"] == "조이상회" and other["price"] == 52500 and other["seller_rating"] == {"score": "100%", "count": 32}
    assert other["shipping"] == "무료배송" and other["delivery_promise"].endswith("도착 예정")
    assert parsers.parse_other_sellers(None) == {"title": None, "count": 0, "results": []}


# ---- best100 / today's new / home best / category tree / suggestions ---------------------

def test_best100_pages():
    cards = parsers.parse_best100(load("best100_all_p1.json"))
    assert len(cards) == 30 and cards[0]["rank"] == 1 and cards[0]["title"] == "해태제과 에이스 과자, 121g, 30개"
    assert cards[0]["unit_price"] == {"price": 80, "per": 10, "unit": "g", "currency": "KRW"} and cards[0]["cashback"] == 1460
    assert cards[0]["is_rocket"] is True and cards[0]["rating"] and cards[0]["reviews"]
    assert len(parsers.parse_best100(load("best100_electronics_p4.json"))) == 10
    assert parsers.parse_best100(load("best100_electronics_p5_empty.json")) == []
    assert parsers.parse_best100(None) == []


def test_todayopen():
    out = parsers.parse_todayopen(load("todayopen.html.gz"))
    assert out["date"] == "2026-10-28" and out["count"] == 48 and out["total_count"] == 298684
    assert out["results"][0]["product_id"] == "9736457529" and out["results"][0]["price"]
    assert parsers.parse_todayopen("")["results"] == []


def test_home_best_units():
    units = parsers.parse_home_best(load("home_best_category.json.gz"))
    assert len(units) == 18 and {u["code"] for u in units} == {code for code, _, _ in refs.HOME_CATEGORIES}
    electronics = next(u for u in units if u["code"] == "ELECTRONICS")
    assert electronics["name"] == "가전 디지털" and electronics["category_id"] == "178255" and len(electronics["results"]) == 30
    assert electronics["hot_keywords"][0]["keyword"] == "태블릿PC" and "channel=" not in electronics["hot_keywords"][0]["link"]
    assert electronics["promotions"][0]["title"] and electronics["results"][0]["image"].startswith("https://thumbnail.coupangcdn.com/")
    assert electronics["results"][0]["rating"] is None      # home cards carry no review block
    assert [u["code"] for u in parsers.parse_home_best(load("home_best_category.json.gz"), {"FOOD"})] == ["FOOD"]


def test_category_tree_and_best_table():
    out = parsers.parse_category_list(load("category_list.json.gz"))
    assert len(out["categories"]) == 15 and out["categories"][7]["name"] == "가전디지털" and out["categories"][7]["id"] == "178255"
    assert out["categories"][0]["children"][0]["name"] == "여성패션" and out["categories"][0]["children"][0]["children"][0]["id"] == "498704"
    assert len(out["themes"]) == 14 and len(out["travel"]) == 2
    # the 15 best100 tabs are the 15 shopping roots
    assert {c["name"] for c in out["categories"]} >= {name for _, name, _ in refs.BEST_CATEGORIES} - {"도서", "반려/애완"}


def test_suggestions():
    assert parsers.parse_suggestions(load("autocomplete.json"))[:2] == ["필기 노트", "스프링 노트"]
    assert parsers.parse_suggestions({}) == []


# ---- seller stores ---------------------------------------------------------------------

def test_store_pages():
    page = parsers.parse_store_page(load("store_noteclub.html.gz"))
    assert page == {"store_id": "119187", "vendor_id": "A00996727", "slug": "A00996727", "name": "주식회사 노트클럽",
                    "description": page["description"], "link": "https://shop.coupang.com/A00996727/433885"}
    brand = parsers.parse_store_page(load("store_cuckoo.html.gz"))
    assert brand["store_id"] == "934" and brand["vendor_id"] == "A00172348" and brand["slug"] == "cuckoo" and brand["name"] == "쿠쿠전자 주식회사"
    assert parsers.is_unknown_store(load("store_unknown.html")) and not parsers.is_unknown_store(load("store_noteclub.html.gz"))
    assert parsers.nuxt_values(load("store_noteclub.html.gz"), ("storeId", "vendorId"))["vendorId"] == "A00996727"
    assert parsers.nuxt_values("", ("storeId",)) == {"storeId": None}


def test_store_profile_follow_and_categories():
    profile = parsers.parse_store_review(load("store_review.json"))
    assert profile["name"] == "주식회사 노트클럽" and profile["rating_count"] == 574 and profile["satisfaction_percent"] == 81
    assert profile["business_number"] == "567-86-03203" and profile["address"].startswith("서울특별시")
    assert parsers.parse_store_review(load("store_review_unknown.json"))["name"] is None
    assert parsers.parse_store_follow(load("store_follow.json")) == 502
    cats = parsers.parse_store_categories(load("store_main_category.json"), load("store_filter.json.gz"))
    assert cats["featured"][0] == {"id": "496759", "name": "미니PC", "image": cats["featured"][0]["image"]}
    assert {"id": "497035", "name": "노트북"} in cats["categories"] and cats["brands"][0]["name"] == "삼성전자"


def test_store_listing_pages():
    out = parsers.parse_store_listing(load("store_listing_p1.json.gz"), 1)
    assert out["pagination"] == {"page": 1, "items_per_page": 20, "total_pages": 37, "total_count": 736} and out["count"] == 20
    assert out["results"][0]["product_id"] == "9749449100" and out["results"][0]["price"] == 7900
    assert any(c["rating"] for c in out["results"])
    past = parsers.parse_store_listing(load("store_listing_past_end.json"), 999)
    assert past["results"] == [] and past["pagination"]["total_count"] == 0
    top = parsers.parse_store_listing(load("store_top_selling.json.gz"))
    assert top["count"] == 23 and top["pagination"]["total_count"] == 736
