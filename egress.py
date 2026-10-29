"""What a session or browser leaving through one exit should announce:
Accept-Language, navigator.languages and the clock of the exit's country,
read from the proxy URL's country tag (`__cr.<cc>` in the
username of some residential providers' URLs). A verbatim slice of the hosted service's egress module — the table of
every country's Accept-Language and the helpers coupang/fetch.py and
patchright_driver.py call; nothing here talks to the network. A proxy URL
without a country tag announces nothing (the session keeps its defaults)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

ACCEPT_LANGUAGE = {
    "us": "en-US,en;q=0.9",
    "gb": "en-GB,en;q=0.9",
    "au": "en-AU,en;q=0.9",
    "ca": "en-CA,en;q=0.9,fr-CA;q=0.8",
    "nz": "en-NZ,en;q=0.9",
    "ie": "en-IE,en;q=0.9",
    "za": "en-ZA,en;q=0.9",
    "in": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
    "sg": "en-SG,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
    "ph": "en-PH,en;q=0.9,fil;q=0.8",
    "my": "ms-MY,ms;q=0.9,en-MY;q=0.8,en;q=0.7",
    "de": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "at": "de-AT,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "ch": "de-CH,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "fr": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "be": "nl-BE,nl;q=0.9,fr;q=0.8,en-US;q=0.7,en;q=0.6",
    "nl": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
    "es": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "it": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "pt": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "pl": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "ru": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "cz": "cs-CZ,cs;q=0.9,en-US;q=0.8,en;q=0.7",
    "sk": "sk-SK,sk;q=0.9,cs;q=0.8,en-US;q=0.7,en;q=0.6",
    "se": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
    "br": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "mx": "es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "th": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
    "vn": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "id": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "tw": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "jp": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "kr": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}
# Every other ISO-3166 country (owner ask 2026-10-28: a Saudi exit announced
# en-SA, a Turkish one en-TR): the language browsers there are usually set to,
# grouped by language, built in the same shape as the rows above (local tag,
# bare language, then English; English-language countries as en-XX,en). The
# rows above win where both exist. Judgement calls: the Maghreb (ma, dz, tn)
# browses in French; Belarus and former-Soviet Central Asia in Russian; the
# Faroes and Greenland in Danish; English-speaking countries, South Asia
# outside Bangladesh, and small territories in English.
_LOCAL_LANGUAGE = {
    "ar": "ae bh eg eh iq jo kw lb ly mr om ps qa sa sd sy ye",
    "fr": "bf bi bj bl cd cf cg ci cm dj dz ga gf gn gp ht km lu ma mc mf mg ml mq nc ne pf pm re sn td tf tg tn wf yt",
    "es": "ar bo cl co cr cu do ec gq gt hn ni pa pe pr py sv uy ve",
    "pt": "ao cv gw mz st tl",
    "nl": "an aw bq cw sr sx",
    "ru": "by kg kz tj tm uz",
    "zh": "cn hk mo",
    "el": "cy gr",
    "da": "dk fo gl",
    "nb": "bv no sj",
    "sq": "al xk",
    "ro": "md ro",
    "sr": "cs me rs",
    "fa": "af ir",
    "de": "li", "it": "sm va", "ca": "ad", "sv": "ax", "ms": "bn", "ko": "kp",
    "tr": "tr", "uk": "ua", "he": "il", "hu": "hu", "fi": "fi", "is": "is",
    "et": "ee", "lv": "lv", "lt": "lt", "bg": "bg", "hr": "hr", "sl": "si",
    "bs": "ba", "mk": "mk", "ka": "ge", "hy": "am", "az": "az", "mn": "mn",
    "bn": "bd", "my": "mm", "km": "kh", "lo": "la", "am": "et", "so": "so",
    "sw": "tz",
    "en": "ag ai aq as bb bm bs bt bw bz cc ck cx dm er fj fk fm gd gg gh gi gm gs gu gy hm im io "
          "je jm ke ki kn ky lc lk lr ls mh mp ms mt mu mv mw na nf ng np nr nu pg pk pn pw rw sb sc "
          "sh sl ss sz tc tk to tt tv ug um vc vg vi vu ws zm zw",
}
for _lang, _codes in _LOCAL_LANGUAGE.items():
    for _cc in _codes.split():
        ACCEPT_LANGUAGE.setdefault(_cc, f"en-{_cc.upper()},en;q=0.9" if _lang == "en" else
                                   f"{_lang}-{_cc.upper()},{_lang};q=0.9,en-US;q=0.8,en;q=0.7")
DIRECT_COUNTRY = "us"   # the GKE pod's own IP (Google Cloud, us-central)
_EXIT_COUNTRY_RE = __import__("re").compile(r"__cr\.([a-z]{2})")


def exit_country(proxy: Optional[str]) -> Optional[str]:
    """The country a `__cr.<cc>`-tagged proxy URL is pinned to, or
    None for direct egress / a URL without a country."""
    if not proxy:
        return None
    match = _EXIT_COUNTRY_RE.search(proxy)
    return match.group(1) if match else None


def accept_language(proxy: Optional[str] = None, country: Optional[str] = None) -> str:
    """The Accept-Language for a session on `proxy` (or an explicit
    `country`): the exit country's list, the pod's own (US) for direct, and
    a generic English list for a code not in the table (every ISO-3166
    country is in it; tests/test_egress_policy.py checks)."""
    cc = (country or exit_country(proxy) or DIRECT_COUNTRY).lower()
    return ACCEPT_LANGUAGE.get(cc) or f"en-{cc.upper()},en;q=0.9"


# ---- the exit's identity (language + clock) -------------------------------------
# The clock a browser on an exit in a single-zone country shows, with no
# lookup. Multi-zone countries (us, ca, au, br, ru, mx, id, ...) are absent on
# purpose: their zone comes from the exit IP (config.exit_geo), and a failed
# lookup keeps the caller's own zone.
TIMEZONE = {
    "gb": "Europe/London", "ie": "Europe/Dublin", "fr": "Europe/Paris", "de": "Europe/Berlin",
    "at": "Europe/Vienna", "ch": "Europe/Zurich", "nl": "Europe/Amsterdam", "be": "Europe/Brussels",
    "lu": "Europe/Luxembourg", "es": "Europe/Madrid", "pt": "Europe/Lisbon", "it": "Europe/Rome",
    "pl": "Europe/Warsaw", "cz": "Europe/Prague", "sk": "Europe/Bratislava", "hu": "Europe/Budapest",
    "ro": "Europe/Bucharest", "bg": "Europe/Sofia", "gr": "Europe/Athens", "se": "Europe/Stockholm",
    "no": "Europe/Oslo", "dk": "Europe/Copenhagen", "fi": "Europe/Helsinki", "ee": "Europe/Tallinn",
    "lv": "Europe/Riga", "lt": "Europe/Vilnius", "hr": "Europe/Zagreb", "si": "Europe/Ljubljana",
    "rs": "Europe/Belgrade", "tr": "Europe/Istanbul", "il": "Asia/Jerusalem",
    "ae": "Asia/Dubai", "sa": "Asia/Riyadh", "qa": "Asia/Qatar", "kw": "Asia/Kuwait", "bh": "Asia/Bahrain",
    "om": "Asia/Muscat", "lb": "Asia/Beirut", "jo": "Asia/Amman", "eg": "Africa/Cairo",
    "ma": "Africa/Casablanca", "za": "Africa/Johannesburg", "ng": "Africa/Lagos", "ke": "Africa/Nairobi",
    "in": "Asia/Kolkata", "pk": "Asia/Karachi", "bd": "Asia/Dhaka", "lk": "Asia/Colombo",
    "sg": "Asia/Singapore", "my": "Asia/Kuala_Lumpur", "th": "Asia/Bangkok", "vn": "Asia/Ho_Chi_Minh",
    "ph": "Asia/Manila", "hk": "Asia/Hong_Kong", "tw": "Asia/Taipei", "cn": "Asia/Shanghai",
    "jp": "Asia/Tokyo", "kr": "Asia/Seoul", "nz": "Pacific/Auckland",
    "ar": "America/Argentina/Buenos_Aires", "cl": "America/Santiago", "co": "America/Bogota",
    "pe": "America/Lima", "uy": "America/Montevideo", "ve": "America/Caracas",
}


def _strip_q(accept: str) -> str:
    return ",".join(t.split(";")[0].strip() for t in accept.split(",") if t.strip())


def languages_for(locale: Optional[str], accept: Optional[str] = None) -> Optional[str]:
    """navigator.languages / Chrome's --accept-lang for `locale`: the full
    q-stripped list ("pl-PL,pl,en-US,en", what Chrome reports for a machine
    set to pl-PL), never a one-tag list. From `accept` when given; else the
    table row the locale heads; a bare language ("de") takes the row of the
    first country browsing in it; a regioned tag heading no row ("zh-Hant-TW")
    keeps itself in front of its language and English. ONE comma string:
    browserforge's tuple form leaves a leading space on every extra entry
    (["pl-PL", " en"], seen 2026-10-28)."""
    if accept:
        return _strip_q(accept)
    if not locale:
        return None
    parts = locale.split("-")
    lang = parts[0].lower()
    if len(parts) == 1:
        for row in ACCEPT_LANGUAGE.values():
            if row.split(",")[0].split("-")[0].lower() == lang:
                return _strip_q(row)
        return f"{lang},en-US,en" if lang != "en" else "en-US,en"
    row = ACCEPT_LANGUAGE.get(parts[-1].lower(), "")
    if row and row.split(",")[0].lower() == locale.lower():
        return _strip_q(row)
    tags = [locale, lang, "en-US", "en"]
    return ",".join(dict.fromkeys(t for t in tags if t))


@dataclass(frozen=True)
class ExitProfile:
    """What a browser or session leaving through one exit should announce.
    `country` None = nothing is known about the exit (direct egress, or a
    proxy URL without a country tag): callers keep their own defaults."""
    country: Optional[str]
    accept_language: Optional[str]
    languages: Optional[str]     # q-stripped, "fr-FR,fr,en-US,en"
    locale: Optional[str]        # "fr-FR"
    timezone: Optional[str]      # IANA zone, or None when only a lookup can tell
    source: Optional[str]        # "geo" (exit IP looked up) | "url" (proxy tag) | None


def exit_profile(proxy: Optional[str] = None, *, geo: Optional[dict] = None,
                 country: Optional[str] = None) -> ExitProfile:
    """The language and clock of the exit behind `proxy`. A successful
    `geo` lookup of the exit (config.exit_geo: countryCode + timezone) is the
    truth and wins over the URL's country tag; an explicit `country` is
    next; the tag last. The zone is the lookup's, else TIMEZONE's for a
    single-zone country, else None."""
    cc, source, zone = None, None, None
    if geo and geo.get("countryCode"):
        cc, source, zone = geo["countryCode"].lower(), "geo", geo.get("timezone")
    elif country:
        cc, source = country.lower(), "url"
    else:
        cc = exit_country(proxy)
        source = "url" if cc else None
    if not cc:
        return ExitProfile(None, None, None, None, None, None)
    accept = ACCEPT_LANGUAGE.get(cc) or f"en-{cc.upper()},en;q=0.9"
    return ExitProfile(country=cc, accept_language=accept, languages=_strip_q(accept),
                       locale=accept.split(",")[0], timezone=zone or TIMEZONE.get(cc),
                       source=source)


