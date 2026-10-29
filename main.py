"""Use the scraper straight from Python — no server needed.

    COUPANG_PROXY=http://user:pass@host:port python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. The function arguments are the validated API params
(coupang/schemas.py): `product` is the dict coupang.refs.resolve_product
makes from an ID or link.
"""
import json
import os

from coupang.api import product_details, products_best, products_search
from coupang.refs import resolve_product

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # the 100 best sellers in electronics, 30 per page (plain HTTP, no proxy needed)
    save("best_electronics.json", products_best(category="178155", collection="bestseller", page=1))

    # a product ID or any coupang.com product link: prices, every option with
    # stock, delivery, seller, specs & certifications (Chrome through COUPANG_PROXY)
    save("product_lg_gram.json", product_details(product=resolve_product("9710533601")))

    # 60 ranked products for a keyword, sorted by sales
    save("search_logitech_mouse.json", products_search(query="logitech mouse", sort="saleCountDesc",
                                                       min_price=None, max_price=None, rocket_only=None))
