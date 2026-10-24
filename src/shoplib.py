"""Shared plumbing for every e-shop fetcher.

- `http_get()`      — one polite HTTP client: robots.txt (allow + Crawl-delay),
                      per-host throttling, retry with backoff, conditional GET cache.
- `read_sitemap()`  — sitemap / sitemap index / .gz → {url: lastmod}.
- `extract_product()` — JSON-LD → microdata → OpenGraph, normalised availability.
- `load_shop()` / `ShopRules` — `shops/<shop>.yaml` merged over `shops/_defaults.yaml`.
- `excluded_finish()` — global ban on finishes we never print with
                        (transparent / natural / silk, see `_defaults.yaml`).

Nothing in here knows about a particular shop; per-shop behaviour lives in
`shops/*.yaml` and the small platform adapters in `src/adapters/`.
"""
from __future__ import annotations
import email.utils, gzip, hashlib, html as html_mod, http.client, json, re, ssl, time, unicodedata
import urllib.error, urllib.parse, urllib.request, urllib.robotparser
from pathlib import Path
import yaml
import config

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
MIN_DELAY = 0.5     # seconds between requests to one host when robots.txt says nothing
MAX_DELAY = 20.0    # cap on Crawl-delay, so a silly robots.txt can't stall the run
HTTP_CACHE = config.FILAMENTS_CACHE / "http"


class FetchError(Exception):
    def __init__(self, url, msg, status=None):
        super().__init__(f"{msg} ({url})")
        self.url, self.status = url, status

class NotFound(FetchError):
    pass

class Disallowed(FetchError):
    pass


# ---------------------------------------------------------------- HTTP ----

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}

def _origin(url: str) -> str:
    p = urllib.parse.urlsplit(url)
    return f"{p.scheme}://{p.netloc}"

def _robots_for(url: str):
    origin = _origin(url)
    if origin not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                rp.parse(r.read().decode("utf-8", errors="replace").splitlines())
        except Exception:
            rp = None          # no robots.txt (or unreachable) → allow, default delay
        _robots[origin] = rp
    return _robots[origin]

def crawl_delay(url: str) -> float:
    rp = _robots_for(url)
    d = (rp.crawl_delay(UA) or rp.crawl_delay("*")) if rp else None
    return min(max(float(d or 0), MIN_DELAY), MAX_DELAY)

def allowed(url: str) -> bool:
    rp = _robots_for(url)
    return rp is None or rp.can_fetch(UA, url)

def _throttle(url: str):
    origin = _origin(url)
    wait = _last_hit.get(origin, 0) + crawl_delay(url) - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_hit[origin] = time.monotonic()

def _cache_paths(url: str):
    key = hashlib.sha1(url.encode()).hexdigest()
    return HTTP_CACHE / f"{key}.json", HTTP_CACHE / f"{key}.body"

def cached_at(url: str) -> float | None:
    """Unix time of the last successful fetch of `url`, or None."""
    meta, _ = _cache_paths(url)
    if not meta.exists():
        return None
    return json.loads(meta.read_text()).get("fetched_at")

def final_url(url: str) -> str:
    """URL the last cached fetch of `url` ended up at after redirects."""
    meta, _ = _cache_paths(url)
    return json.loads(meta.read_text()).get("final_url", url) if meta.exists() else url

def _retry_after(value: str) -> float | None:
    """Seconds from a Retry-After header: delta-seconds or an HTTP-date."""
    value = (value or "").strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - time.time()) if when else None

def http_get(url: str, *, binary=False, referer=None, retries=3, use_cache=True,
             max_age: float | None = None, check_robots=True):
    """GET `url` politely. Returns str (or bytes when binary=True).

    With `use_cache`, the body is stored under filaments/.cache/http and the next
    request is conditional (ETag / Last-Modified). When `max_age` seconds haven't
    passed since the last fetch, the cached body is returned without any request.
    Raises NotFound on 404/410, Disallowed on robots.txt, FetchError otherwise.
    """
    meta_p, body_p = _cache_paths(url)
    meta = json.loads(meta_p.read_text()) if use_cache and meta_p.exists() and body_p.exists() else None
    if meta and max_age is not None and time.time() - meta.get("fetched_at", 0) < max_age:
        body = body_p.read_bytes()
        return body if binary else body.decode("utf-8", errors="replace")
    if check_robots and not allowed(url):
        raise Disallowed(url, "disallowed by robots.txt")

    headers = {"User-Agent": UA, "Accept-Language": "cs,en;q=0.8"}
    if referer:
        headers["Referer"] = referer
    if meta:
        if meta.get("etag"):          headers["If-None-Match"] = meta["etag"]
        if meta.get("last_modified"): headers["If-Modified-Since"] = meta["last_modified"]

    last_err = None
    for attempt in range(retries + 1):
        _throttle(url)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or body[:2] == b"\x1f\x8b":
                    body = gzip.decompress(body)
                if use_cache:
                    HTTP_CACHE.mkdir(parents=True, exist_ok=True)
                    body_p.write_bytes(body)
                    meta_p.write_text(json.dumps({
                        "url": url, "final_url": r.geturl(), "fetched_at": time.time(),
                        "etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified")}))
                break
        except urllib.error.HTTPError as e:
            if e.code == 304 and meta:
                meta["fetched_at"] = time.time()
                meta_p.write_text(json.dumps(meta))
                body = body_p.read_bytes()
                break
            if e.code in (404, 410):
                raise NotFound(url, f"HTTP {e.code}", e.code)
            last_err = FetchError(url, f"HTTP {e.code}", e.code)
            if e.code not in (408, 425, 429, 500, 502, 503, 504):
                raise last_err
            delay = _retry_after(e.headers.get("Retry-After", "")) or 2 ** (attempt + 1)
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                http.client.HTTPException, ssl.SSLError) as e:      # IncompleteRead, RemoteDisconnected, …
            last_err = FetchError(url, f"{type(e).__name__}: {getattr(e, 'reason', e)}")
            delay = 2 ** (attempt + 1)
        if attempt < retries:
            time.sleep(min(delay, 60))
    else:
        raise last_err
    return body if binary else body.decode("utf-8", errors="replace")


# ------------------------------------------------------------- sitemap ----

_LOC = re.compile(r"<(?:\w+:)?loc>\s*(?:<!\[CDATA\[)?\s*([^<\]\s]+)\s*(?:\]\]>)?\s*</(?:\w+:)?loc>", re.I)
_ENTRY = re.compile(r"<(?:\w+:)?(url|sitemap)>(.*?)</(?:\w+:)?\1>", re.I | re.S)
_LASTMOD = re.compile(r"<(?:\w+:)?lastmod>\s*([^<\s]+)\s*</", re.I)

def parse_sitemap(xml: str):
    """→ (kind, [(loc, lastmod|None)]) where kind is 'index' or 'urlset'."""
    kind = "index" if re.search(r"<(?:\w+:)?sitemapindex\b", xml, re.I) else "urlset"
    out = []
    for _tag, body in _ENTRY.findall(xml):
        loc = _LOC.search(body)
        if not loc:
            continue
        lm = _LASTMOD.search(body)
        out.append((html_mod.unescape(loc.group(1)), lm.group(1) if lm else None))
    return kind, out

def read_sitemap(url: str, child_filter: str | None = None, _depth=0) -> dict[str, str | None]:
    """All page URLs reachable from a sitemap (index), with their lastmod.
    `child_filter` (regex) limits which child sitemaps of an index are followed."""
    xml = http_get(url, use_cache=False)
    kind, entries = parse_sitemap(xml)
    if kind == "urlset":
        return dict(entries)
    out: dict[str, str | None] = {}
    if _depth > 3:
        return out
    for loc, _lm in entries:
        if child_filter and not re.search(child_filter, loc):
            continue
        out.update(read_sitemap(loc, None, _depth + 1))
    return out


# ------------------------------------------------- product extraction ----

_AVAIL = {
    "instock": "InStock", "instoreonly": "InStock", "onlineonly": "InStock", "limitedavailability": "InStock",
    "outofstock": "OutOfStock", "soldout": "OutOfStock", "discontinued": "OutOfStock",
    "preorder": "PreOrder", "presale": "PreOrder", "backorder": "PreOrder",
}

def norm_availability(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return "InStock" if v else "OutOfStock"
    s = re.sub(r"[^a-z]", "", str(v).rsplit("/", 1)[-1].lower())
    return _AVAIL.get(s)

def stock_label(availability: str | None) -> str:
    """Legacy `stock` field (Czech label) derived from schema.org availability."""
    return {"InStock": "Skladem", "OutOfStock": "Vyprodáno", "PreOrder": "Na objednávku"}.get(availability, "?")

def _jsonld_nodes(html: str):
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip(), strict=False)
        except ValueError:
            continue
        stack = [data]
        while stack:
            n = stack.pop()
            if isinstance(n, list):
                stack.extend(n)
            elif isinstance(n, dict):
                yield n
                for k in ("@graph", "hasVariant", "mainEntity", "itemListElement"):
                    if k in n:
                        stack.append(n[k])

def _types(n):
    t = n.get("@type")
    return {x.lower() for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}

def _first(v):
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict):
        v = v.get("url") or v.get("contentUrl") or v.get("name")
    return v

def _meta(html, *names):
    for name in names:
        for pat in (rf'<meta[^>]+(?:property|name|itemprop)=["\']{re.escape(name)}["\'][^>]*content=["\']([^"\']*)["\']',
                    rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name|itemprop)=["\']{re.escape(name)}["\']'):
            m = re.search(pat, html, re.I)
            if m and m.group(1).strip():
                return html_mod.unescape(m.group(1).strip())
    return None

def extract_product(html: str, url: str = "") -> dict:
    """Best-effort product facts from a product page.
    Keys: name, brand, image, availability, sku, gtin, source (which layer answered)."""
    p = {"name": None, "brand": None, "image": None, "availability": None, "sku": None, "gtin": None, "source": []}

    # 1) JSON-LD Product
    for n in _jsonld_nodes(html):
        if not _types(n) & {"product", "productgroup"}:
            continue
        p["name"]  = p["name"]  or _first(n.get("name"))
        p["brand"] = p["brand"] or _first(n.get("brand"))
        p["image"] = p["image"] or _first(n.get("image"))
        p["sku"]   = p["sku"]   or n.get("sku")
        p["gtin"]  = p["gtin"]  or n.get("gtin13") or n.get("gtin")
        offers = n.get("offers")
        for o in (offers if isinstance(offers, list) else [offers] if offers else []):
            if isinstance(o, dict) and p["availability"] is None:
                p["availability"] = norm_availability(o.get("availability"))
        if "jsonld" not in p["source"]:
            p["source"].append("jsonld")

    # 2) microdata
    if p["availability"] is None:
        m = (re.search(r'itemprop=["\']availability["\'][^>]*(?:href|content)=["\']([^"\']+)', html, re.I)
             or re.search(r'(?:href|content)=["\']([^"\']*schema\.org/\w+)["\'][^>]*itemprop=["\']availability', html, re.I))
        if m:
            p["availability"] = norm_availability(m.group(1))
            p["source"].append("microdata")
    if p["sku"] is None:
        p["sku"] = _meta(html, "sku")
    if p["brand"] is None:
        m = re.search(r'itemprop=["\']brand["\'].{0,300}?itemprop=["\']name["\'][^>]*content=["\']([^"\']+)', html, re.I | re.S)
        p["brand"] = html_mod.unescape(m.group(1)) if m else None

    # 3) visible <h1>, then OpenGraph / product meta (og:title often carries promo text)
    if p["name"] is None:
        m = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, re.S | re.I)
        h1 = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip() if m else ""
        p["name"] = h1 or None
    p["image"] = p["image"] or _meta(html, "og:image", "og:image:secure_url", "twitter:image")
    p["name"]  = p["name"]  or _meta(html, "og:title", "twitter:title")
    if p["availability"] is None:
        p["availability"] = norm_availability(_meta(html, "product:availability", "og:availability"))
        if p["availability"]:
            p["source"].append("og")

    if p["name"]:
        p["name"] = clean_title(html_mod.unescape(str(p["name"])))
    if p["image"]:
        p["image"] = urllib.parse.urljoin(url, html_mod.unescape(str(p["image"])))
    return p


_PLACEHOLDER_IMG = re.compile(r"logo|placeholder|no-?image|noimage|default-image|blank\.", re.I)

def product_page(url: str, *, referer=None, max_age=None) -> dict:
    """Fetch + extract one product page; NotFound when the shop redirected the URL
    away (e.g. to a search page) and the landing page is not a product."""
    html = http_get(url, referer=referer, max_age=max_age)
    facts = extract_product(html, url)
    landed = final_url(url)
    moved = urllib.parse.urlsplit(landed).path.rstrip("/") != urllib.parse.urlsplit(url).path.rstrip("/")
    if moved and not ({"jsonld", "microdata"} & set(facts["source"])):
        raise NotFound(url, f"redirected to non-product page {landed}")
    if facts["image"] and _PLACEHOLDER_IMG.search(urllib.parse.urlsplit(facts["image"]).path):
        facts["image"] = None
    return facts


# --------------------------------------------------------------- rules ----

def _fold(s: str) -> str:
    """lowercase + strip diacritics, so 'průhledná' and 'pruhledna' match the same rule."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return s.lower()

def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _fold(s)).strip("-")

def load_defaults() -> dict:
    p = config.SHOP_DEFAULTS
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}

def _finish_patterns(defaults: dict | None = None) -> dict[str, re.Pattern]:
    d = defaults if defaults is not None else load_defaults()
    return {name: re.compile(rx, re.I) for name, rx in (d.get("exclude_finishes") or {}).items()}

_FINISH_CACHE: dict[str, re.Pattern] | None = None

def excluded_finish(*texts, patterns: dict[str, re.Pattern] | None = None) -> str | None:
    """Name of the banned finish (e.g. 'silk') found in any of `texts`, else None.
    Texts are diacritics-folded and lowercased before matching."""
    global _FINISH_CACHE
    if patterns is None:
        if _FINISH_CACHE is None:
            _FINISH_CACHE = _finish_patterns()
        patterns = _FINISH_CACHE
    blob = " | ".join(_fold(t) for t in texts if t)
    for name, rx in patterns.items():
        if rx.search(blob):
            return name
    return None


def region_labels(defaults: dict | None = None) -> dict[str, str]:
    """{region key: label} in display order, from `regions:` in shops/_defaults.yaml."""
    return dict((defaults if defaults is not None else load_defaults()).get("regions") or {})

def validate_regions(regions, defaults: dict, where: str) -> list[str]:
    """A shop's `regions:` list; every entry must be a key of the defaults' `regions:` map."""
    known = region_labels(defaults)
    if not regions or not isinstance(regions, list):
        raise ValueError(f"{where}: `regions:` must be a non-empty list (known: {', '.join(known)})")
    bad = [r for r in regions if r not in known]
    if bad:
        raise ValueError(f"{where}: unknown region {', '.join(bad)} (known: {', '.join(known)})")
    return list(regions)


class ShopRules:
    """Compiled `shops/<key>.yaml` merged over `_defaults.yaml`.

    include / exclude: regexes on the diacritics-folded URL path; a URL is
    accepted when it matches ANY include and NO exclude (defaults + shop).
    materials: ordered {label: regex}, the first one matching URL path or title wins.
    """
    def __init__(self, key: str, cfg: dict, defaults: dict):
        self.key = key
        self.cfg = cfg
        self.name = cfg["name"]
        self.platform = cfg["platform"]
        self.base = cfg.get("base", "").rstrip("/")
        self.include = [re.compile(r, re.I) for r in cfg.get("include") or [".*"]]
        self.exclude = [re.compile(r, re.I) for r in (defaults.get("exclude") or []) + (cfg.get("exclude") or [])]
        mats = cfg.get("materials") or defaults.get("materials") or {}
        self.materials = [(label, re.compile(rx, re.I)) for label, rx in mats.items()]
        self.overrides = cfg.get("overrides") or {}
        self.pins = cfg.get("pins") or []
        self.slug_rx = re.compile(cfg["slug_regex"]) if cfg.get("slug_regex") else None
        # Most shops put the material in the slug; set false where only the title has it.
        self.material_in_url = bool(cfg.get("material_in_url", defaults.get("material_in_url", True)))
        self.max_new = int(cfg.get("max_new_per_run", defaults.get("max_new_per_run", 300)))
        self.refresh_days = float(cfg.get("refresh_days", defaults.get("refresh_days", 7)))
        self.min_keep_ratio = float(cfg.get("min_keep_ratio", defaults.get("min_keep_ratio", 0.8)))
        self.finishes = _finish_patterns(defaults)
        self.regions = validate_regions(cfg.get("regions"), defaults, f"shops/{key}.yaml")

    def path(self, url: str) -> str:
        return _fold(urllib.parse.unquote(urllib.parse.urlsplit(url).path))

    def accepts(self, url: str) -> bool:
        path = self.path(url)
        return (any(r.search(path) for r in self.include)
                and not any(r.search(path) for r in self.exclude)
                and (not self.material_in_url or self.material(path) is not None))

    def rejects_title(self, title: str) -> bool:
        """Title-level exclude (bundles/samples that hide behind an innocent slug)."""
        t = _fold(title)
        return any(r.search(t) for r in self.exclude)

    def material(self, *texts) -> str | None:
        blob = " ".join(_fold(t) for t in texts if t)
        for label, rx in self.materials:
            if rx.search(blob):
                return label
        return None

    def slug(self, url: str) -> str:
        path = urllib.parse.urlsplit(url).path
        if self.slug_rx:
            m = self.slug_rx.search(path)
            if m:
                return m.group(1)
        return [s for s in path.split("/") if s][-1]


def list_shops() -> list[str]:
    return sorted(p.stem for p in config.SHOPS_DIR.glob("*.yaml") if not p.stem.startswith("_"))

def load_shop(key: str) -> ShopRules:
    cfg = yaml.safe_load((config.SHOPS_DIR / f"{key}.yaml").read_text(encoding="utf-8"))
    return ShopRules(key, cfg, load_defaults())

def shop_regions() -> dict[str, list[str]]:
    """{shop display name: regions} for every shops/*.yaml."""
    return {r.name: r.regions for r in map(load_shop, list_shops())}


# ---------------------------------------------------------- naming ----

_NOISE = re.compile(
    r"\b(filament|filamenty|struna|refill|nahradni\s+napln|spool|cívka|civka|"
    r"\d+[.,]?\d*\s*(?:mm|kg|g)\b|1[.,]75|2[.,]85|nfc)\b", re.I)

_PRICE = re.compile(r"(?:\b(?:jen|pouze|už|uz|od|za)\s+)*(?:za\s+)?\d[\d\s.,]*\s*(?:(?:,-\s*)?(?:Kč|Kc|CZK|€|EUR)\b|,-)", re.I)
_SYMBOLS = re.compile(r"[\u2600-\u27BF\U0001F000-\U0001FAFF\uFE0F]")

def clean_title(title: str) -> str:
    """Product title without shop suffixes (' | Shop', ' :: Shop'), prices or emoji.
    Prices must never enter the data (see CLAUDE.md, 'No prices, anywhere')."""
    t = re.split(r"\s+(?:::|[|–—])\s+", title or "")[0]
    t = _SYMBOLS.sub(" ", _PRICE.sub(" ", t))
    return re.sub(r"\s+", " ", t).strip(" -,")

_LEGAL = re.compile(r"\s*(?:,?\s*(?:s\.\s?r\.\s?o\.|a\.\s?s\.|gmbh|ltd\.?|inc\.?|sp\.\s?z\s?o\.\s?o\.)|\boriginal\b)\s*$", re.I)

def clean_brand(brand: str | None) -> str | None:
    """'AURAPOL s.r.o.' → 'AURAPOL', 'BambuLab original' → 'BambuLab'."""
    if not brand:
        return brand
    b = str(brand).strip()
    while True:
        nb = _LEGAL.sub("", b).strip(" ,")
        if nb == b:
            return b or None
        b = nb

def _brand_words(brand: str | None) -> list[str]:
    """Brand plus its parts and a space-less form: 'Spectrum + The Filament' →
    ['Spectrum + The Filament', 'Spectrum', 'The Filament', 'TheFilament', …]."""
    if not brand:
        return []
    parts = [p.strip() for p in re.split(r"\s*[+&/]\s*", brand) if p.strip()]
    words = [brand, *parts, *(p.replace(" ", "") for p in parts)]
    words += [re.sub(r"(?<=[a-z])(?=[A-Z])", " ", p) for p in parts]      # BambuLab → Bambu Lab
    return sorted(set(words), key=len, reverse=True)

def _tidy_case(t: str) -> str:
    """'ŠEDÁ CLOUD' → 'Šedá Cloud' when the whole name is shouted; mixed case stays."""
    letters = [c for c in t if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return " ".join(w if len(w) <= 2 else w.capitalize() for w in t.split())
    return t

def derive_color_name(title: str, brand: str | None, material: str | None) -> str:
    """'Filament AURAPOL PLA Cloud Nine 1,75 mm 1 kg' → 'Cloud Nine'."""
    t = clean_title(html_mod.unescape(title or ""))
    for word in filter(None, [*_brand_words(clean_brand(brand)), material, "PLA+", "PLA", "PETG", "PET-G"]):
        t = re.sub(rf"(?<![\w-]){re.escape(word)}(?![\w-])", " ", t, flags=re.I)
    t = _NOISE.sub(" ", t)
    t = re.sub(r"[\"“”„]", " ", t)
    t = re.sub(r"\(\s*[;,/]?\s*\)", " ", t)
    t = re.sub(r"[\s,;:/\-–]+", " ", t).strip(" -,.")
    t = _tidy_case(t)
    return t[:1].upper() + t[1:] if t else (title or "").strip()
