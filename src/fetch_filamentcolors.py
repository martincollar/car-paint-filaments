"""Fetch the FilamentColors.xyz library via its REST API.

FilamentColors has 2000+ pre-measured filament swatches with hex + CIELAB
baked in, so no image measurement step. We filter to PLA/PETG only and tag
every record with library="intl" to keep this catalog separate from the
Czech-shop catalog ("cz").
"""
import json, sys, os, time, urllib.request, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import config

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
API = "https://filamentcolors.xyz/api/swatch/"
OUT = config.FILAMENTS_SOURCES
DATA = config.FILAMENTS_DATA

# Keep PLA / PETG. Skip exotic materials (TPU, PCTG, ASA/ABS) for the car-paint use case.
KEEP_TYPES = {"PLA", "PETG"}

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def download_image(img_url, local_name, referer=None):
    local = OUT / local_name
    if local.exists(): return local_name
    try:
        req = urllib.request.Request(img_url, headers={"User-Agent": UA, **({"Referer": referer} if referer else {})})
        with urllib.request.urlopen(req, timeout=30) as r:
            local.write_bytes(r.read())
        return local_name
    except Exception as e:
        print(f"  IMG fail {local_name}: {e}"); return None

def hex_to_rgb(h):
    h = h.lstrip("#")
    try: return [int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)]
    except Exception: return None

results = []
page = 1
url = API
kept = skipped = 0
while url:
    try:
        data = fetch_json(url)
    except Exception as e:
        print(f"  page {page} FAIL: {e}"); break
    page_hits = 0
    for sw in data["results"]:
        ft = (sw.get("filament_type") or {}).get("name", "")
        if ft not in KEEP_TYPES:
            skipped += 1
            continue
        hex_v = sw.get("hex_color", "").upper().lstrip("#")
        rgb = hex_to_rgb(hex_v)
        if not rgb: continue
        mfr = (sw.get("manufacturer") or {}).get("name", "Unknown")
        name = sw.get("color_name", "")
        slug = sw.get("slug") or f"fc-{sw['id']}"
        img_url = sw.get("card_img") or sw.get("image_front")
        local = None
        if img_url:
            ext = os.path.splitext(urllib.parse.urlparse(img_url).path)[1] or ".jpg"
            local = download_image(img_url, f"fc-{sw['id']}{ext}", referer="https://filamentcolors.xyz/")
        buy = sw.get("mfr_purchase_link") or sw.get("amazon_purchase_link") or f"https://filamentcolors.xyz/swatch/{slug}/"
        results.append({
            "slug": slug,
            "brand": mfr,
            "material": ft,
            "color_name": name,
            "shop": "FilamentColors",
            "library": "intl",
            "url": buy,
            "image_url": img_url,
            "local_image": local,
            "stock": "available" if sw.get("is_available") else "unavailable",
            "rgb": rgb,
            "hex": "#" + hex_v,
            "lab": [sw.get("lab_l"), sw.get("lab_a"), sw.get("lab_b")],
            "confidence": "api_measured_hex",
        })
        kept += 1
        page_hits += 1
    print(f"  page {page}: {len(data['results'])} total, {page_hits} kept  (running total: {kept})")
    url = data.get("next")
    page += 1
    time.sleep(0.3)

(DATA / "filaments_raw_filamentcolors.json").write_text(
    json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n{kept} kept (PLA/PETG), {skipped} skipped (other materials)  →  filaments_raw_filamentcolors.json")
