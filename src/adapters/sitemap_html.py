"""Sitemap discovery + one HTML product page per item (Upgates, Shoptet, generic)."""
import shoplib

def discover(rules):
    cfg = rules.cfg
    urls = shoplib.read_sitemap(cfg["sitemap"], cfg.get("sitemap_filter"))
    return {u: {"lastmod": lm, "data": None} for u, lm in urls.items() if rules.accepts(u)}

def product(rules, url, cand, max_age):
    return shoplib.product_page(url, referer=rules.base + "/", max_age=max_age)
