"""Fetch every shop described in shops/*.yaml → filaments/data/filaments_raw_<shop>.json.

Per shop:
  1. discover candidate product URLs (sitemap / Shopify JSON) + `pins:` from the YAML,
     filtered by the shop's include/exclude rules;
  2. fetch each product page politely (robots.txt, Crawl-delay, retry, HTTP cache —
     known pages are re-fetched only after `refresh_days`, new ones capped by
     `max_new_per_run`), read JSON-LD/microdata/og;
  3. drop non-PLA/PETG items and banned finishes (transparent/natural/silk);
  4. write the raw JSON, keeping the last good record (`stale: true`) when a page
     fails, and refusing to shrink the shop below `min_keep_ratio`;
  5. update filaments/data/catalog.lock.json (accepted + rejected, for git review)
     and filaments/data/fetch_report.json, and print the +new / −gone diff.

Usage:
    python fetch_all.py                    # every shop
    python fetch_all.py --shop hubacek3d   # one (repeatable)
    python fetch_all.py --dry-run          # discovery only: what would be new / gone
    python fetch_all.py --refresh          # ignore refresh_days, re-read every page
    python fetch_all.py --force            # write even if the shrink guard trips
Exit code 1 when any shop failed or tripped the guard.
"""
import argparse, json, os, sys, time, urllib.parse
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import config, shoplib, adapters

TODAY = date.today().isoformat()


def raw_path(key):
    return config.FILAMENTS_DATA / f"filaments_raw_{key}.json"

def load_json(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

write_json = config.write_json


def candidates(rules, adapter):
    """slug → {url, lastmod, data, pin}. Pins override discovered entries with the same slug."""
    found = {}
    for url, info in adapter.discover(rules).items():
        found.setdefault(rules.slug(url), {"url": url, "pin": None, **info})
    for pin in rules.pins:
        slug = pin.get("slug") or rules.slug(pin["url"])
        prev = found.get(slug, {})
        found[slug] = {"url": pin["url"], "lastmod": prev.get("lastmod"), "data": prev.get("data"), "pin": pin}
    return found


def needs_network(url, lastmod, max_age):
    at = shoplib.cached_at(url)
    if at is None or max_age is None or time.time() - at >= max_age:
        return True
    return bool(lastmod and lastmod[:10] > date.fromtimestamp(at).isoformat())


def image_name(rules, slug, image_url):
    ext = os.path.splitext(urllib.parse.urlsplit(image_url).path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"
    return f"{rules.key}-{shoplib.slugify(slug)}{ext}"


def ensure_image(rules, image_url, local, prev_image_url, page_url):
    path = config.FILAMENTS_SOURCES / local
    if path.exists() and (prev_image_url in (None, image_url)):
        return local
    try:
        path.write_bytes(shoplib.http_get(image_url, binary=True, referer=page_url, use_cache=False,
                                          check_robots=False))
        return local
    except shoplib.FetchError as e:
        print(f"    IMG fail {local}: {e}")
        return local if path.exists() else None


def fetch_shop(rules, args, lock, report):
    adapter = adapters.get(rules.platform)
    prev_records = {r["slug"]: r for r in load_json(raw_path(rules.key), [])}
    shop_lock = lock.setdefault(rules.key, {"products": {}, "rejected": {}})
    rep = report[rules.key] = {"status": "ok", "date": TODAY, "candidates": 0, "records": 0,
                               "new": [], "gone": [], "not_found": [], "stale": [], "errors": [],
                               "deferred": 0, "rejected": {}}
    print(f"\n=== {rules.name} ({rules.platform}) ===")
    try:
        cands = candidates(rules, adapter)
    except Exception as e:          # FetchError, or a shop answering garbage: keep the old records
        e = e if isinstance(e, shoplib.FetchError) else f"{type(e).__name__}: {e}"
        rep.update(status="fail", errors=[f"discovery: {e}"])
        print(f"  FAIL discovery: {e} — keeping previous {len(prev_records)} records")
        return
    rep["candidates"] = len(cands)
    known = set(shop_lock["products"]) | set(shop_lock["rejected"])
    print(f"  {len(cands)} candidate URLs ({len(set(cands) - known)} never seen)")
    if args.dry_run:
        rep["status"] = "dry-run"
        for s in sorted(set(cands) - known):
            print(f"  + {cands[s]['url']}")
        for s in sorted(set(shop_lock["products"]) - set(cands)):
            print(f"  − {shop_lock['products'][s]['url']}")
        return

    max_age = None if args.refresh else rules.refresh_days * 86400
    budget = args.max_new if args.max_new is not None else rules.max_new
    records, rejected = {}, {}

    def reject(slug, reason):
        rejected[slug] = reason
        rep["rejected"][reason.split(":")[0]] = rep["rejected"].get(reason.split(":")[0], 0) + 1

    # Known slugs first so the budget only ever delays *new* products.
    order = sorted(cands, key=lambda s: (s not in prev_records and s not in shop_lock["rejected"], s))
    for slug in order:
        c = cands[slug]
        pin, ov = c["pin"] or {}, rules.overrides.get(slug, {})
        url = c["url"]
        if ov.get("skip"):
            reject(slug, "override:skip"); continue
        # Cheap pre-checks on the URL alone, before spending a request.
        if not pin and shoplib.excluded_finish(slug, url, patterns=rules.finishes):
            reject(slug, f"finish:{shoplib.excluded_finish(slug, url, patterns=rules.finishes)}"); continue
        if not c.get("data") and needs_network(url, c.get("lastmod"), max_age):
            if budget <= 0 and slug not in prev_records:
                rep["deferred"] += 1; continue
            budget -= slug not in prev_records
        try:
            facts = adapter.product(rules, url, c, max_age)
        except shoplib.NotFound as e:
            rep["not_found"].append(url); print(f"  404  {url}"); continue
        except Exception as e:      # FetchError, or a page the extractor chokes on
            e = e if isinstance(e, shoplib.FetchError) else f"{type(e).__name__}: {e} ({url})"
            if slug in prev_records:
                records[slug] = {**prev_records[slug], "stale": True}
                rep["stale"].append(url)
            rep["errors"].append(str(e)); print(f"  ERR  {e}")
            continue

        title = facts.get("name") or ""
        material = ov.get("material") or pin.get("material") or rules.material(rules.path(url), title)
        if not material:
            reject(slug, "material"); continue
        if not pin and rules.rejects_title(title):
            reject(slug, "title"); continue
        brand = (ov.get("brand") or pin.get("brand") or shoplib.clean_brand(facts.get("brand"))
                 or rules.cfg.get("default_brand") or rules.name)
        color = ov.get("color_name") or pin.get("color_name") or shoplib.derive_color_name(title, brand, material)
        finish = shoplib.excluded_finish(slug, url, title, color, patterns=rules.finishes)
        if finish:
            reject(slug, f"finish:{finish}"); continue
        image_url = ov.get("image_url") or pin.get("image_url") or facts.get("image")
        if not image_url:
            reject(slug, "no-image"); continue
        prev = prev_records.get(slug, {})
        local = ov.get("local_image") or pin.get("local_image") or prev.get("local_image") or image_name(rules, slug, image_url)
        local = ensure_image(rules, image_url, local, prev.get("image_url"), url)
        if not local:
            rep["errors"].append(f"image: {image_url}"); continue

        avail = facts.get("availability")
        records[slug] = {"slug": slug, "brand": brand, "material": material, "color_name": color,
                         "shop": rules.name, "url": url, "image_url": image_url, "local_image": local,
                         "availability": avail, "stock": shoplib.stock_label(avail),
                         "title": title, "last_ok": TODAY}
        print(f"  OK   {material:5s} {brand[:14]:14s} {color[:34]:34s} {avail or '?'}")

    # Previously known products that vanished from discovery: gone (reported, dropped).
    rep["gone"] = sorted(prev_records[s]["url"] for s in set(prev_records) - set(cands))
    rep["new"] = sorted(records[s]["url"] for s in set(records) - set(prev_records))
    rep["records"] = len(records)

    if prev_records and len(records) < rules.min_keep_ratio * len(prev_records) and not args.force:
        rep["status"] = "guard"
        print(f"  GUARD {len(records)} < {rules.min_keep_ratio:.0%} of previous {len(prev_records)} — not written (use --force)")
        return
    write_json(raw_path(rules.key), [records[s] for s in sorted(records)])
    products = {}
    for s in sorted(records):
        old = shop_lock["products"].get(s, {})
        products[s] = {"url": records[s]["url"], "first_seen": old.get("first_seen", TODAY), "last_seen": TODAY}
    shop_lock["products"] = products
    shop_lock["rejected"] = {s: rejected[s] for s in sorted(rejected)}
    if rep["errors"] or rep["not_found"]:
        rep["status"] = "partial"
    print(f"  → {len(records)} records  (+{len(rep['new'])} −{len(rep['gone'])}, {len(rep['stale'])} stale, "
          f"{len(rep['not_found'])} 404, {rep['deferred']} deferred, rejected {rep['rejected']})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--shop", action="append", help="shop key (file name in shops/), repeatable")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-new", type=int)
    args = ap.parse_args()

    keys = args.shop or shoplib.list_shops()
    config.FILAMENTS_SOURCES.mkdir(parents=True, exist_ok=True)
    lock = load_json(config.CATALOG_LOCK, {})
    report = load_json(config.FETCH_REPORT, {})
    for key in keys:
        try:
            fetch_shop(shoplib.load_shop(key), args, lock, report)
        except Exception as e:      # one broken shop must not cost the others their run
            print(f"  FAIL {key}: {type(e).__name__}: {e}")
            report[key] = {"status": "fail", "date": TODAY, "errors": [f"{type(e).__name__}: {e}"]}
        if not args.dry_run:          # persist after every shop: a crash keeps finished work
            write_json(config.CATALOG_LOCK, {k: lock[k] for k in sorted(lock)})
            write_json(config.FETCH_REPORT, {k: report[k] for k in sorted(report)})

    bad = [k for k in keys if report[k]["status"] in ("fail", "guard")]
    print("\n" + "  ".join(f"{k}:{report[k]['status']}" for k in keys))
    if bad:
        print(f"✗ problems in: {', '.join(bad)} — see {config.FETCH_REPORT}")
        sys.exit(1)

if __name__ == "__main__":
    main()
