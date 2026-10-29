# 🛒 Coupang Scraper

Coupang Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Coupang data for free.

## ✨ What Can I Get?

- 🛍️ **Full details on any Coupang product** — price tiers, coupons & cashback, every option with stock, delivery date, seller registration, specs & other sellers' prices
- 🔍 **Search & browse the whole catalogue** — 60 ranked products per page, Rocket & price filters, best sellers, today's 420K+ new listings & the full category tree
- ⭐ **Every review & question** — full text, star breakdown, photos, survey answers, helpful votes & the seller's answers
- 🏪 **Seller stores** — rating, followers, business registration, top sellers & the whole catalogue by category

## 💻 Example: A Full Coupang Product

```json
{
  "product_id": "9710533601",
  "item_id": "27479813418",
  "vendor_item_id": "95669754881",
  "title": "LG전자 2026 그램북 AI 15 코어 Ultra5",
  "option_title": "타이탄 블랙 · 256GB · 8GB · WIN11 Home · 15U50U-GR5CK",
  "brand": "LG전자",
  "link": "https://www.coupang.com/vp/products/9710533601?itemId=27479813418&vendorItemId=95669754881",
  "images": ["https://thumbnail.coupangcdn.com/thumbnails/remote/640x640ex/image/vendor_inventory/c277/6b6bb983f0f69a984dbd0773880e00c5dea3d1e587e347e23992963d90f4.jpg"],
  "price": {
    "price": 1286990, "sale_price": 1286990, "coupon_price": 1286990, "original_price": null, "currency": "KRW",
    "tiers": [{ "type": "SALES", "label": "쿠팡판매가", "price": 1286990 }],
    "cashback": 50000
  },
  "shipping": { "type": "FREE", "fee": 0, "original_fee": 2500, "message": "무료배송", "currency": "KRW" },
  "delivery": { "type": "VENDOR_DELIVERY", "message": "화요일 11/3 도착 예정 (판매자배송)", "arrival": { "date": "2026-11-03T23:59:59.999000+09:00", "charge_type": "FREE" } },
  "availability": { "is_sold_out": false, "buyable_quantity": 1000, "is_in_stock": true },
  "rating": 4.7,
  "reviews": 486,
  "social_proof": { "recent_buyers": 439, "message": "400명 이상", "four_five_star_reviews": 453 },
  "category": { "id": "2236", "name": "노트북", "path": ["가전디지털", "컴퓨터/게임", "컴퓨터"] },
  "options": [
    { "name": "색상", "type": "IMAGE", "values": [{ "value_id": "4262556855", "name": "Black" }] },
    { "name": "저장용량 × RAM용량 × 운영체제 × 모델명/품번", "type": "TEXT", "values": [{ "value_id": "615546820,1664382973,432645197,2007944944", "name": "256GB × 8GB × WIN11 Home × 15U50U-GR5CK" }] }
  ],
  "variants": [
    { "item_id": "27707936944", "vendor_item_id": "95078145678", "item_name": "LG전자 2026 그램 AI 15 코어 Ultra5, 타이탄 블랙, 256GB, 16GB, Free DOS, 15 AI 15UD50U-GX5JK", "price": 1146240, "currency": "KRW", "is_sold_out": false, "is_almost_sold_out": true, "buyable_quantity": 6 }
  ],
  "other_seller_count": 8,
  "seller": { "name": "주식회사 커스텀씨앤씨", "is_coupang_retail": false, "is_marketplace": true, "business_number": "534-88-03361", "country": "KR" },
  "policies": { "delivery_method": "순차배송", "delivery_company": "로젠택배", "is_bundle_shipping": true, "return_charge": "20,000원 - 단, 고객 변심의 경우에만 발생 - 도서산간 및 일부 지역 추가비용 발생" },
  "essentials": [
    { "title": "품명 및 모델명", "value": "노트북 / 15U50U" },
    { "title": "KC 인증정보", "value": "본품: R-R-LGE-15U50T , ZU10202-24004H / 모듈: R-C-INT-AX211D2W" }
  ],
  "other_sellers": [
    { "vendor_item_id": "95669754881", "seller": "주식회사 커스텀씨앤씨", "price": 1286990, "currency": "KRW", "shipping": "무료배송", "delivery_promise": "11/3(화) 도착 예정", "seller_rating": { "count": 14 } }
  ]
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Coupang Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/coupang-scraper
cd coupang-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/products/best?category=electronics"
```

```json
{
  "count": 100,
  "per_page": 30,
  "current_page": 1,
  "total_pages": 4,
  "next": "http://localhost:8000/products/best?category=electronics&page=2",
  "previous": null,
  "category": { "id": "178155", "name": "가전디지털", "slug": "electronics", "link": "https://www.coupang.com/np/best100/bestseller/178155" },
  "collection": "bestseller",
  "results": [
    {
      "rank": 1,
      "product_id": "9506325370",
      "item_id": "28325572495",
      "vendor_item_id": "95375952128",
      "title": "맥스틸 25W GaN 2포트 PD PPS 초고속 충전기 C타입 USB 멀티 어댑터, 1개, 화이트",
      "link": "https://www.coupang.com/vp/products/9506325370?itemId=28325572495&vendorItemId=95375952128",
      "image": "https://thumbnail.coupangcdn.com/thumbnails/remote/230x230ex/image/retail/images/2026/05/06/10/3/925c3cb7-84e7-4669-afe7-f28456cf98bf.jpg",
      "price": 4900,
      "original_price": 12000,
      "discount_rate": 59,
      "currency": "KRW",
      "unit_price": { "price": 4900, "per": 1, "unit": "개", "currency": "KRW" },
      "rating": 5,
      "reviews": 2725,
      "is_rocket": true,
      "delivery_promise": "내일(금) 도착 보장",
      "cashback": 200,
      "is_sold_out": false,
      "is_sponsored": false
    }
  ]
}
```

All 13 endpoints are now live at `http://localhost:8000`.

Best sellers, today's new products, best by category, the category tree and search suggestions work from most connections as plain HTTP. The other eight endpoints (product search, details, reviews, questions, category pages and the three seller endpoints) sit behind Coupang's Akamai bot protection, which admits only a real Chrome on a Korean IP. For them you need Google Chrome installed and, from outside South Korea, a **sticky residential proxy in South Korea**:

```bash
COUPANG_PROXY="http://user:pass@host:port" python run.py
```

On the first walled request Chrome opens once, proves itself with one search (about 30–60 seconds) and then stays open, so every request after that takes a few seconds. If Coupang answers 403 on every page, switch the proxy to another Korean IP and restart.

## 📚 Endpoints

13 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Product Details | `/products/details` | Prices, coupons, every option with stock, delivery, seller, specs & other sellers in one call |
| Search Products | `/products/search` | 60 ranked products for a keyword with filters & related keywords |
| Product Reviews | `/products/reviews` | 10 reviews per page: rating, full text, photos, survey answers, votes & star breakdown |
| Product Questions | `/products/questions` | Customer questions with the seller's answers, 15 per page |
| Best Sellers | `/products/best` | The last 7 days' top 100 in any category, 30 per page |
| New Products Today | `/products/new` | 48 of today's new listings plus the day's total |
| Category Products | `/categories/products` | Any category, 60 per page, sortable, with price & Rocket filters |
| Best By Category | `/categories/best` | Top 30 per category with hot keywords & promotions |
| Category List | `/categories/list` | The full 3-level category tree with IDs and links |
| Seller Details | `/sellers/details` | Store rating, followers, product count, business registration & top sellers |
| Seller Products | `/sellers/products` | A seller's whole catalogue, 20 per page, by store category |
| Seller Categories | `/sellers/categories` | The categories and brands a seller's catalogue spans |
| Search Suggestions | `/products/suggest` | Coupang's own search-box suggestions for a partial keyword |

Every `product`, `category` and `seller` param takes an ID or any coupang.com link. Pass a product link with `itemId` and `vendorItemId` to get a specific option; a bare product ID gets the site's default option.

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-coupang-scraper-free-200-calls/pricing) — 200 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-coupang-scraper-free-200-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-coupang-scraper-free-200-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/products/search",
    params={"query": "logitech mouse", "sort": "best_selling"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Coupang Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Coupang%20Scraper%20API.)

[![Ask Us by Email about Coupang Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Coupang%20Scraper%20API&body=I%20need%20help%20using%20the%20Coupang%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/coupang-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/coupang-scraper)
