"""Configuration for the Coupang Scraper. Everything can be set with an
environment variable.

    PORT           port the API listens on (default 8000)
    COUPANG_PROXY  proxy URL, e.g. http://user:pass@host:port (default: none —
                   your own IP). Coupang serves Korean shoppers: the open
                   feeds (best sellers, today's new products, the category
                   tree, search suggestions, store pages) work from most
                   connections without it, but product search, product
                   details / reviews / questions, category pages and seller
                   catalogues need a STICKY residential proxy in South Korea.
                   The same proxy is used for the browser (search / category /
                   product pages and the seller JSON, where Coupang's Akamai
                   bot protection admits only a real Chrome) — keep one exit
                   IP for the life of the process.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

COUPANG_PROXY = os.environ.get("COUPANG_PROXY") or None

# Chromes kept open for the walled pages (one per proxy; one is plenty).
COUPANG_BROWSER_SLOTS = 1
# Attempts per call when Coupang refuses the browser's exit (each one
# relaunches Chrome through COUPANG_PROXY — with one fixed exit, retrying
# rarely helps, so keep it low).
COUPANG_BOX_ATTEMPTS = 2


def coupang_proxy():
    """The exit for the open feeds (None = your own IP)."""
    return os.environ.get("COUPANG_PROXY") or None


def coupang_seller_proxy():
    """The exit for shop.coupang.com's open store JSON — a Korean residential proxy."""
    return os.environ.get("COUPANG_PROXY") or None


def coupang_browser_proxy():
    """The exit Chrome uses for the search / category / product pages."""
    return os.environ.get("COUPANG_PROXY") or None


def exit_geo(proxy, timeout=12):
    """Geo of a proxy's exit IP, looked up THROUGH the proxy (ip-api.com).
    Returns {countryCode, regionName, city, timezone, query} or None on any
    failure — Chrome then keeps the clock of the proxy's country tag, else
    this machine's."""
    try:
        import requests
        r = requests.get("http://ip-api.com/json/?fields=status,countryCode,regionName,city,timezone,query",
                         proxies={"http": proxy, "https": proxy}, timeout=timeout)
        d = r.json()
        if d.get("status") == "success" and d.get("timezone"):
            return d
    except Exception:
        pass
    return None
