"""Drives the Coupang pages only a real browser can, with a Google Chrome
(patchright) on this machine.

Coupang's Akamai bot protection walls the search, category and product
pages (and the product page's own reviews / questions JSON) for every plain
HTTP client. coupang/fetch.py asks this module for them (`ExitPool.fetch_any`):
one headed Chrome per proxy opens the Coupang home page, proves itself with
one search, then loads every requested page as a normal navigation and
returns the DOM — coupang/fetch.py parses it. Reviews and questions run as
in-page fetch() calls on the product's own page. The Chrome is kept open
between requests and closed when Coupang refuses its exit.

The seller profile and catalogue JSON of shop.coupang.com run the same way,
as in-page calls on the store's own page (a plain-HTTP replay of a browser's
cookies is cut off after a few calls).

Needs Google Chrome installed (patchright drives it). Coupang refuses
headless Chrome, so a window opens. From outside South Korea, or when
Coupang's own 403 page ("요청하신 페이지의 사용권한이 없습니다") answers every
page, set COUPANG_PROXY to a STICKY residential proxy in South Korea.

Same interface as the hosted service's client for its browser servers:
ExitPool, fetch_any() and the exception classes, so coupang/ runs unchanged."""
import threading
import time

SITE = "https://www.coupang.com"
HOME = SITE + "/"
PROBE_SEARCH = SITE + "/np/search?q=%EB%85%B8%ED%8A%B8%EB%B6%81&channel=user"   # 노트북 (laptop)
PAGE_HEADER = "x-coupang-page"
CHALLENGE_MARKERS = ("sec-if-cpt-container", "sec-bc-tile-container")
ACCESS_DENIED_MARKERS = ("<TITLE>Access Denied</TITLE>", "errors.edgesuite.net")
COUPANG_403_MARKERS = ("요청하신 페이지의 사용권한이 없습니다", "사용권한이 제한된 페이지입니다")
CHALLENGE_WAIT = 20
SETTLE_WAIT = 2.5
BLOCK_RESOURCES = ("image", "font", "media")
BROWSER_IDLE = 300          # close a Chrome nobody used for this long


class BoxUnavailable(Exception):
    """Chrome could not start on this machine (not installed, no display)."""

    def __init__(self, message="", candidate=None):
        super().__init__(message)
        self.candidate = candidate
        self.proxy = None


class BoxRefused(Exception):
    """Coupang refused this exit (Akamai 403 / challenge, or Coupang's own 403 page)."""

    def __init__(self, message="", candidate=None):
        super().__init__(message)
        self.candidate = candidate
        self.proxy = None


# ---- page verdicts ------------------------------------------------------------------

def is_challenge(text):
    head = (text or "")[:8000]
    return any(m in head for m in CHALLENGE_MARKERS)


def is_refusal(status, text, title):
    head = (text or "")[:12000]
    if status in (403, 429):
        return True
    if any(m in head for m in ACCESS_DENIED_MARKERS):
        return True
    return (title or "").strip() == "Access Denied" or any(m in head for m in COUPANG_403_MARKERS)


def _wiggle(page, step):
    page.mouse.move(160 + step * 31, 240 + step * 9, steps=8)
    page.mouse.move(520 + step * 7, 380 + step * 13, steps=12)
    page.mouse.wheel(0, 420)


# ---- one Chrome per proxy --------------------------------------------------------------

def _launch(proxy):
    try:
        from patchright_driver import PatchrightDriver
        return PatchrightDriver(proxy, headless=False, locale="ko-KR", geoip_timezone=bool(proxy),
                                block_resources=list(BLOCK_RESOURCES))
    except Exception as e:
        raise BoxUnavailable(f"could not start Chrome: {type(e).__name__}: {e}")


class _Browser:
    def __init__(self, proxy):
        self.proxy = proxy
        self.lock = threading.Lock()
        self.driver = None
        self.last_use = time.monotonic()

    def _settled(self, res):
        status = res.get("status")
        html = res.get("html") or ""
        deadline = time.monotonic() + CHALLENGE_WAIT
        while is_challenge(html) and time.monotonic() < deadline:
            time.sleep(0.5)
            try:
                html = self.driver.content() or ""
            except Exception:
                html = ""
                continue
            if html and not is_challenge(html):
                status = 200
        try:
            title = self.driver.title() or ""
        except Exception:
            title = ""
        return status, title, html

    def goto(self, url, referer):
        try:
            res = self.driver.nav(url, referer=referer, mode="csr") or {}
        except Exception as e:
            raise BoxRefused(f"coupang: navigation failed ({type(e).__name__}: {str(e)[:120]})")
        status, title, html = self._settled(res)
        if is_challenge(html):
            raise BoxRefused(f"coupang: Akamai's challenge page never cleared on this exit ({url})")
        if is_refusal(status, html, title):
            raise BoxRefused(f"coupang: refused on this exit (HTTP {status}, title {title!r}, {url.split('?')[0]}); "
                             "set COUPANG_PROXY to a sticky residential proxy in South Korea (or another one)")
        return status or 200, html, res.get("url") or url

    def warm(self):
        self.driver = _launch(self.proxy)
        try:
            try:
                self.goto(HOME, "https://www.google.com/")
            except BoxRefused as e:
                print(f"coupang: home page refused, trying the probe search anyway ({e})", flush=True)
            for step in range(3):
                self.driver.call(lambda page, s=step: _wiggle(page, s))
                time.sleep(0.6)
            status, html, _ = self.goto(PROBE_SEARCH, HOME)
            if "self.__next_f.push" not in html:
                raise BoxRefused(f"coupang: the probe search did not render on this exit (HTTP {status})")
        except Exception:
            self.close()
            raise

    def fetch_one(self, url, method, headers, body=None):
        headers = dict(headers or {})
        page_url = (headers.pop(PAGE_HEADER, "") or "").strip()
        if page_url:
            return self._in_page_json(page_url, url, headers, method, body)
        status, html, final = self.goto(url, HOME)
        time.sleep(SETTLE_WAIT)
        try:
            html = self.driver.content() or html
        except Exception:
            pass
        return {"status": status, "headers": {}, "body": html, "final_url": final}

    def _in_page_json(self, page_url, url, headers, method="GET", body=None):
        """A same-origin JSON call run inside `page_url` (a product page for
        reviews / questions, a shop.coupang.com store page for the seller
        profile and catalogue): the page's own Akamai sensor keeps the
        cookies valid, where a replay over plain HTTP is cut off."""
        try:
            current = self.driver.current_url() or ""
        except Exception:
            current = ""
        if current.split("#")[0] != page_url.split("#")[0]:
            self.goto(page_url, HOME)
            time.sleep(SETTLE_WAIT)
        clean = {k: v for k, v in headers.items() if k.lower() in ("accept", "content-type", "x-requested-with")}
        method = (method or "GET").upper()
        if method == "GET":
            r = self.driver.get(url, headers=clean or None, referrer=page_url)
        else:
            r = self.driver.request(method, url, headers=clean or None, body=body, referrer=page_url)
        if not r.status_code and r.error:
            raise BoxRefused(f"coupang: in-page fetch failed: {r.error}")
        out = {"status": r.status_code, "headers": dict(r.headers or {}), "body": r.text, "final_url": r.url or url}
        if is_refusal(out["status"], out["body"], ""):
            raise BoxRefused(f"coupang: the product JSON was refused on this exit (HTTP {out['status']})")
        return out

    def close(self):
        driver, self.driver = self.driver, None
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass


_browsers = {}
_browsers_lock = threading.Lock()


def _browser(proxy):
    with _browsers_lock:
        now = time.monotonic()
        for key, b in list(_browsers.items()):
            if key != proxy and b.driver is not None and now - b.last_use > BROWSER_IDLE and not b.lock.locked():
                b.close()
        b = _browsers.get(proxy)
        if b is None:
            b = _browsers[proxy] = _Browser(proxy)
        return b


def fetch(site, url=None, urls=None, method="GET", headers=None, body=None, proxy=None,
          variant="", session=None, timeout=None):
    """One page (or several) on the kept Chrome for `proxy`."""
    b = _browser(proxy)
    with b.lock:
        b.last_use = time.monotonic()
        if b.driver is None:
            b.warm()
        try:
            if urls:
                return [b.fetch_one(u, method, headers, body) for u in urls]
            return b.fetch_one(url, method, headers, body)
        except BoxRefused:
            b.close()
            raise
        except Exception as e:
            b.close()
            raise BoxUnavailable(f"coupang: Chrome failed: {type(e).__name__}: {e}")


def fetch_any(site, candidates, url=None, urls=None, method="GET", headers=None, body=None, variant="",
              timeout=None):
    """fetch() on the first candidate [(proxy, session), ...] -> (index, result);
    a refusal carries the index so the caller rotates that exit."""
    proxy = candidates[0][0] if candidates else None
    try:
        return 0, fetch(site, url=url, urls=urls, method=method, headers=headers, body=body, proxy=proxy,
                        variant=variant, timeout=timeout)
    except (BoxRefused, BoxUnavailable) as e:
        e.candidate = 0
        e.proxy = proxy
        raise


# ---- sticky exits per site (the hosted client's holder, unchanged) ------------------------

class ExitPool:
    """Sticky proxy exits for one site's browsers: `mint` returns a fresh
    proxy URL (or None for your own IP), `size` how many are kept per key.
    With COUPANG_PROXY there is exactly one exit, so every slot is the same
    proxy and rotate() only relaunches Chrome on it."""

    def __init__(self, site, mint, size=1):
        self.site = site
        self._mint = mint
        self._size = size
        self._lock = threading.Lock()
        self._slots = {}
        self._next = {}
        self._filled = {}

    def _n(self):
        n = self._size() if callable(self._size) else self._size
        return max(1, int(n or 1))

    def _mint_for(self, key):
        return self._mint()

    def get(self, key=""):
        with self._lock:
            n = self._n()
            slots = self._slots.setdefault(key, [])
            filled = self._filled.setdefault(key, set())
            while len(slots) < n:
                slots.append(None)
            del slots[n:]
            i = self._next.get(key, 0) % n
            self._next[key] = (i + 1) % n
            if i not in filled:
                slots[i] = self._mint_for(key)
                filled.add(i)
            return slots[i]

    def all(self, key=""):
        with self._lock:
            n = self._n()
            slots = self._slots.setdefault(key, [])
            filled = self._filled.setdefault(key, set())
            while len(slots) < n:
                slots.append(None)
            del slots[n:]
            for i in range(n):
                if i not in filled:
                    slots[i] = self._mint_for(key)
                    filled.add(i)
            return list(slots)

    def fetch_any(self, site, key="", sessions=None, **kw):
        exits = self.all(key)
        candidates = [(p, sessions(p) if sessions else None) for p in exits]
        try:
            index, out = fetch_any(site, candidates, **kw)
        except (BoxRefused, BoxUnavailable) as e:
            if e.candidate is not None and 0 <= e.candidate < len(exits):
                e.proxy = exits[e.candidate]
            raise
        return exits[index], out

    def rotate(self, proxy, key=""):
        with self._lock:
            slots = self._slots.get(key) or []
            filled = self._filled.setdefault(key, set())
            for i, cur in enumerate(slots):
                if cur == proxy and i in filled:
                    slots[i] = self._mint_for(key)
                    return True
            return False

    def current(self, key=""):
        with self._lock:
            return list(self._slots.get(key) or [])

    def reset(self, key=None):
        with self._lock:
            if key is None:
                self._slots.clear(); self._next.clear(); self._filled.clear()
            else:
                self._slots.pop(key, None); self._next.pop(key, None); self._filled.pop(key, None)
