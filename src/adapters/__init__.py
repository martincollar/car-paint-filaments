"""Platform adapters. Each module exposes:

    discover(rules) -> {url: {"lastmod": str|None, "data": dict|None}}
        Every candidate product URL the shop publishes that passes `rules.accepts()`.
        `data` is pre-fetched product facts when the platform hands them out in bulk.

    product(rules, url, cand, max_age) -> dict
        Product facts (name, brand, image, availability, …) as returned by
        `shoplib.extract_product()`. May raise shoplib.FetchError / NotFound.

Pins (`pins:` in the shop YAML) are added by fetch_all.py for every platform.
"""
from . import sitemap_html, shopify, manual

ADAPTERS = {
    "upgates": sitemap_html,   # Smart3D, Aurapol, Hubacek3D
    "shoptet": sitemap_html,   # 3DFox
    "generic": sitemap_html,   # any shop with a sitemap + JSON-LD/microdata/og product pages
    "shopify": shopify,        # Fillamentum (/products.json)
    "manual":  manual,         # only pinned URLs (Prusa variants, Na3D photos)
}

def get(platform: str):
    try:
        return ADAPTERS[platform]
    except KeyError:
        raise SystemExit(f"unknown platform {platform!r}; known: {', '.join(ADAPTERS)}")
