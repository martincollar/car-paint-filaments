"""Fetch the FilamentColors.xyz library via its REST API.

FilamentColors has 2000+ pre-measured filament swatches with hex + CIELAB
baked in, so no image measurement step. We filter to PLA/PETG only and tag
every record with library="intl" to keep this catalog separate from the
Czech-shop catalog ("cz").

Goes through `shoplib.http_get()` like the shop fetchers (robots.txt, throttling,
retry, conditional-GET cache). The raw file is only rewritten after every API
page came back, and not when the library would shrink below `min_keep_ratio`
of the previous run (shops/_defaults.yaml); `--force` accepts a shrink.

Usage:
    python fetch_filamentcolors.py [--force]
Exit code 1 when a page failed or the shrink guard tripped (previous file kept).
"""
import argparse, json, os, sys, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import config, shoplib
from color_tools import hex_to_rgb

API = "https://filamentcolors.xyz/api/swatch/"
RAW = config.FILAMENTS_DATA / "filaments_raw_filamentcolors.json"

# Keep PLA / PETG. Skip exotic materials (TPU, PCTG, ASA/ABS) for the car-paint use case.
KEEP_TYPES = {"PLA", "PETG"}

def download_image(img_url, local_name, referer=None):
    local = config.FILAMENTS_SOURCES / local_name
    if local.exists(): return local_name
    try:
        local.write_bytes(shoplib.http_get(img_url, binary=True, referer=referer, use_cache=False,
                                           check_robots=False))
        return local_name
    except shoplib.FetchError as e:
        print(f"  IMG fail {local_name}: {e}"); return None

def record(sw):
    """One API swatch → raw record, or None when it isn't a usable PLA/PETG swatch."""
    ft = (sw.get("filament_type") or {}).get("name", "")
    if ft not in KEEP_TYPES:
        return None
    hex_v = (sw.get("hex_color") or "").upper().lstrip("#")
    rgb = hex_to_rgb(hex_v)
    if not rgb:
        return None
    slug = sw.get("slug") or f"fc-{sw['id']}"
    img_url = sw.get("card_img") or sw.get("image_front")
    local = None
    if img_url:
        ext = os.path.splitext(urllib.parse.urlparse(img_url).path)[1] or ".jpg"
        local = download_image(img_url, f"fc-{sw['id']}{ext}", referer="https://filamentcolors.xyz/")
    avail = "InStock" if sw.get("is_available") else "OutOfStock"
    return {
        "slug": slug,
        "brand": (sw.get("manufacturer") or {}).get("name", "Unknown"),
        "material": ft,
        "color_name": sw.get("color_name", ""),
        "shop": "FilamentColors",
        "library": "intl",
        "url": sw.get("mfr_purchase_link") or sw.get("amazon_purchase_link") or f"https://filamentcolors.xyz/swatch/{slug}/",
        "image_url": img_url,
        "local_image": local,
        "availability": avail,
        "stock": "available" if avail == "InStock" else "unavailable",
        "rgb": rgb,
        "hex": "#" + hex_v,
        "lab": [sw.get("lab_l"), sw.get("lab_a"), sw.get("lab_b")],
        "confidence": "api_measured_hex",
    }

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--force", action="store_true", help="write even if the shrink guard trips")
    args = ap.parse_args()

    config.FILAMENTS_SOURCES.mkdir(parents=True, exist_ok=True)
    results, skipped, page, url = [], 0, 1, API
    while url:
        try:
            data = json.loads(shoplib.http_get(url))
        except (shoplib.FetchError, ValueError) as e:
            print(f"  page {page} FAIL: {e} — keeping the previous {RAW.name}")
            sys.exit(1)
        hits = [r for r in map(record, data["results"]) if r]
        skipped += len(data["results"]) - len(hits)
        results += hits
        print(f"  page {page}: {len(data['results'])} total, {len(hits)} kept  (running total: {len(results)})")
        url = data.get("next")
        page += 1

    prev = len(json.loads(RAW.read_text(encoding="utf-8"))) if RAW.exists() else 0
    ratio = float(shoplib.load_defaults().get("min_keep_ratio", 0.8))
    if prev and len(results) < ratio * prev and not args.force:
        print(f"GUARD {len(results)} < {ratio:.0%} of previous {prev} — not written (use --force)")
        sys.exit(1)
    config.write_json(RAW, results)
    print(f"\n{len(results)} kept (PLA/PETG), {skipped} skipped (other materials)  →  {RAW.name}")

if __name__ == "__main__":
    main()
