"""Cache TTL per /coupang/* endpoint (cache.py, keyed on the validated
params). Coupang prices move through the day (Rocket deals, coupons,
quantity-based instant discounts), so anything carrying a price is cached
for hours, not days; catalog structure for a day. Search and product pages
cost a browser navigation on the box, so they are never served uncached
twice within their TTL."""
from datetime import timedelta

# One search page (60 cards with prices): a box navigation per miss.
SEARCH_CACHE = timedelta(hours=6)
# A category listing page: prices on every card, a box navigation per miss.
CATEGORY_CACHE = timedelta(hours=6)
# The product record: price / coupon / stock of the landing option.
PRODUCT_CACHE = timedelta(hours=6)
# Reviews and Q&A arrive slowly; a page a few hours old is fine.
REVIEWS_CACHE = timedelta(hours=12)
QUESTIONS_CACHE = timedelta(hours=12)
# best100 is "the last 7 days' sales"; it re-ranks a few times a day.
BEST_CACHE = timedelta(hours=6)
# Today's new arrivals change with the calendar day (Korea).
NEW_CACHE = timedelta(hours=3)
# The home "best by category" units + hot keywords.
HOME_BEST_CACHE = timedelta(hours=6)
# The category tree is rebuilt by Coupang's merchandising, rarely.
CATEGORIES_CACHE = timedelta(hours=24)
# Search suggestions are popularity-ranked, slow-moving.
SUGGEST_CACHE = timedelta(hours=24)
# A seller's profile + top sellers; the business registration never moves.
SELLER_CACHE = timedelta(hours=12)
# One page of a store's catalogue (prices).
SELLER_PRODUCTS_CACHE = timedelta(hours=6)
# The store's category / brand filter lists.
SELLER_CATEGORIES_CACHE = timedelta(hours=24)
