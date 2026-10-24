"""Shopify: the whole catalogue comes from /products.json, no per-page requests."""
import json
import shoplib

def _json(url, **kw):
    """GET a Shopify JSON endpoint; an HTML error/maintenance page becomes a FetchError."""
    body = shoplib.http_get(url, **kw)
    try:
        return json.loads(body)
    except ValueError:
        raise shoplib.FetchError(url, f"not JSON: {body[:60]!r}")

def discover(rules):
    out, page = {}, 1
    while True:
        products = _json(f"{rules.base}/products.json?limit=250&page={page}", use_cache=False).get("products") or []
        if not products:
            return out
        for p in products:
            url = f"{rules.base}/products/{p['handle']}"
            if not rules.accepts(url):
                continue
            variants = p.get("variants") or []
            images = p.get("images") or []
            out[url] = {"lastmod": p.get("updated_at"), "data": {
                "name": p.get("title"), "brand": p.get("vendor"),
                "image": images[0]["src"].split("?")[0] if images else None,
                "availability": shoplib.norm_availability(any(v.get("available") for v in variants)) if variants else None,
                "sku": (variants[0].get("sku") if variants else None), "gtin": None, "source": ["shopify-json"]}}
        page += 1

def product(rules, url, cand, max_age):
    if cand.get("data"):
        return cand["data"]
    # pinned handle that /products.json didn't list: the per-product JSON endpoint
    p = _json(url.split("?")[0] + ".json", max_age=max_age).get("product")
    if not p:
        raise shoplib.FetchError(url, "no product in JSON")
    variants, images = p.get("variants") or [], p.get("images") or []
    return {"name": p.get("title"), "brand": p.get("vendor"),
            "image": images[0]["src"].split("?")[0] if images else None,
            "availability": shoplib.norm_availability(any(v.get("available") for v in variants)) if variants else None,
            "sku": None, "gtin": None, "source": ["shopify-json"]}
