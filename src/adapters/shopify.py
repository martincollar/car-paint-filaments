"""Shopify: the whole catalogue comes from /products.json, no per-page requests."""
import json
import re
import shoplib

def _json(url, **kw):
    """GET a Shopify JSON endpoint; an HTML error/maintenance page becomes a FetchError."""
    body = shoplib.http_get(url, **kw)
    try:
        return json.loads(body)
    except ValueError:
        raise shoplib.FetchError(url, f"not JSON: {body[:60]!r}")

def _split_variants(rules, p, spec):
    """One candidate per colour of a product that keeps its colours as variants.

    spec (`split_variants:` in the shop YAML): `option` = name of the colour option,
    `keep` = regex a variant title must match (1.75 mm / 1 kg, not refills). The first
    matching variant of each colour wins; its own photo (variant image_id) is the colour's image.
    """
    opts = [o["name"].strip().lower() for o in p.get("options") or []]
    try:
        ci = opts.index(str(spec["option"]).strip().lower())
    except ValueError:
        return {}
    keep = re.compile(spec["keep"], re.I) if spec.get("keep") else None
    images = {i["id"]: i["src"].split("?")[0] for i in p.get("images") or []}
    by_variant = {vid: i["src"].split("?")[0] for i in p.get("images") or [] for vid in i.get("variant_ids") or []}
    out, seen = {}, set()
    for v in p.get("variants") or []:
        color = v.get(f"option{ci + 1}")
        if not color or color in seen or (keep and not keep.search(v.get("title") or "")):
            continue
        seen.add(color)
        # the variant's own photo only: falling back to the product's first image would give every colour the same one
        feat = (v.get("featured_image") or {}).get("src")
        image = (feat or "").split("?")[0] or images.get(v.get("image_id")) or by_variant.get(v["id"])
        url = f"{rules.base}/products/{p['handle']}?variant={v['id']}"
        slug = shoplib.slugify(f"{p['handle']}-{color}")
        out[url] = {"slug": slug, "lastmod": p.get("updated_at"), "data": {
            "name": f"{p.get('title')} {color}", "color": color, "brand": p.get("vendor"), "image": image,
            "availability": shoplib.norm_availability(bool(v.get("available"))),
            "sku": v.get("sku"), "gtin": None, "source": ["shopify-json"]}}
    return out

def discover(rules):
    out, page = {}, 1
    split = rules.cfg.get("split_variants")
    while True:
        products = _json(f"{rules.base}/products.json?limit=250&page={page}", use_cache=False).get("products") or []
        if not products:
            return out
        for p in products:
            url = f"{rules.base}/products/{p['handle']}"
            if not rules.accepts(url):
                continue
            if split:
                out.update(_split_variants(rules, p, split))
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
