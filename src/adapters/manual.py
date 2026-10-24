"""Shops without per-colour pages in their sitemap: only `pins:` from the YAML.

The pinned page is still fetched (cached) so availability is read from its
structured data; a pin's `image_url` wins over the page's og:image.
"""
import shoplib

def discover(rules):
    return {}

def product(rules, url, cand, max_age):
    facts = shoplib.product_page(url, referer=rules.base + "/", max_age=max_age)
    if not (cand.get("pin") or {}).get("availability_from_page", True):
        facts["availability"] = None       # one page shared by many colours: its stock says nothing per colour
    return facts
