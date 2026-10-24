"""Measure every filament from every `filaments_raw_*.json` and build filaments.json.

Reads all raw shop fetches in `filaments/data/filaments_raw*.json`, measures each
image with `color_tools.filament_rgb()` **unless the raw record already has rgb/hex**
(FilamentColors.xyz gives pre-measured hex via API), deduplicates by (library, url, slug)
and writes a single `filaments/data/filaments.json`.

Finishes banned in `shops/_defaults.yaml` (`exclude_finishes`: transparent, natural,
silk) are dropped here too — fetch_all.py already skips them, this also covers the
intl library and any hand-made raw file.

Manual colors from `filaments/color_overrides.json` ({slug: {hex, note}}) win over
the measurement; the measured value is kept as `measured_hex` for comparison.

Each record carries a `library` field (defaults to "cz" for the Czech shop pool)
so downstream `compute_matches.py` can keep catalogs separate.

Usage:
    python measure_filaments.py
"""
import json, sys, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from color_tools import filament_rgb, rgb_to_hex, rgb_to_lab, delta_e_2000
import config, shoplib

# filament_rgb() can't measure white/black filaments: white pixels are dropped as studio
# background and near-black ones as shadow, so the median lands on the spool or box.
# Flag records whose name contradicts the measured lightness; fix them in color_overrides.json.
WHITE_WORDS = ("white", "bílá", "bila", "snowflake", "snow")
BLACK_WORDS = ("black", "černá", "cerna")

def suspicious_neutral(rec):
    if rec.get("confidence") != "measured_dominant_hue" or not rec.get("rgb"):
        return None
    name = rec.get("color_name", "").lower()
    L = float(rgb_to_lab(rec["rgb"])[0])
    if any(w in name for w in WHITE_WORDS) and L < 75:
        return f"named white but L={L:.0f}"
    if any(w in name for w in BLACK_WORDS) and L > 30:
        return f"named black but L={L:.0f}"
    return None

def load_overrides():
    p = config.FILAMENT_COLOR_OVERRIDES
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def apply_override(rec, ov):
    hx = ov["hex"].lstrip("#")
    if rec.get("hex"):
        rec["measured_hex"] = rec["hex"]
    rec["rgb"] = [int(hx[i:i+2], 16) for i in (0, 2, 4)]
    rec["hex"] = "#" + hx.upper()
    rec["confidence"] = "manual_override"
    rec.pop("error", None)
    return rec

_HINTS = None

def measure_hints(brand):
    """filament_rgb() options for this brand from shops/_defaults.yaml `measure_hints`."""
    global _HINTS
    if _HINTS is None:
        import re
        _HINTS = [(re.compile(rx, re.I), opts) for rx, opts in (shoplib.load_defaults().get("measure_hints") or {}).items()]
    out = {}
    for rx, opts in _HINTS:
        if rx.search(brand or ""):
            out.update(opts)
    return out

def measure_record(r):
    rec = dict(r)
    # Default library tag — Czech-shop fetchers predate the field
    rec.setdefault("library", "cz")
    # If raw already has rgb (e.g. FilamentColors API), keep it as-is
    if r.get("rgb") and r.get("hex"):
        rec.setdefault("confidence", "preset_from_source")
        return rec
    if not r.get("local_image"):
        rec["error"] = "no local image"
        return rec
    path = config.FILAMENTS_SOURCES / r["local_image"]
    try:
        rgb, npx = filament_rgb(path, name=r.get("color_name"), **measure_hints(r.get("brand")))
        if rgb is None:
            rec["error"] = "no measurable pixels"
            return rec
        rec["rgb"] = list(rgb)
        rec["hex"] = rgb_to_hex(rgb)
        rec["pixel_count"] = npx
        rec["confidence"] = "measured_dominant_hue"
    except Exception as e:
        rec["error"] = str(e)
    return rec

def main():
    raws = sorted(glob.glob(str(config.FILAMENTS_DATA / "filaments_raw*.json")))
    all_rows, banned = [], {}
    for p in raws:
        rows = json.loads(Path(p).read_text(encoding="utf-8"))
        kept = []
        for r in rows:
            r.setdefault("shop", "?")
            finish = shoplib.excluded_finish(r.get("slug"), r.get("color_name"), r.get("title"), r.get("url"))
            if finish:
                banned[finish] = banned.get(finish, 0) + 1
                continue
            kept.append(r)
        all_rows.extend(kept)
        print(f"loaded {len(kept):5d} from {Path(p).name}  ({len(rows) - len(kept)} banned finish)")
    print(f"dropped banned finishes: {banned or 'none'}")

    # Previous measurement, so a changed colour can be reviewed (review_sheet.py "Changed")
    prev = {}
    if config.FILAMENTS_JSON.exists():
        for r in json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8")):
            if r.get("rgb"):
                prev[(r.get("library", "cz"), r.get("url"), r.get("slug"))] = r

    measured = [measure_record(r) for r in all_rows]

    overrides = load_overrides()
    used = set()
    for r in measured:
        if r.get("slug") in overrides:
            apply_override(r, overrides[r["slug"]])
            used.add(r["slug"])
    print(f"applied {len(used)}/{len(overrides)} color overrides")
    for slug in sorted(set(overrides) - used):
        print(f"  ! override for unknown slug: {slug}")

    # Dedup by (library, url, slug): keep first (earliest raw file wins).
    # Slug is part of the key because one page can carry many colours (Na3D).
    seen = set(); dedup = []
    for r in measured:
        key = (r.get("library", "cz"), r.get("url"), r.get("slug"))
        if key[1] and key in seen: continue
        if key[1]: seen.add(key)
        dedup.append(r)

    changed = 0
    for r in dedup:
        old = prev.get((r.get("library", "cz"), r.get("url"), r.get("slug")))
        if old and r.get("rgb") and delta_e_2000(old["rgb"], r["rgb"]) >= 3:
            r["previous_hex"] = old["hex"]
            changed += 1
    print(f"{changed} colours changed by ΔE ≥ 3 since the last run (see review_sheet.py)")
    for r in dedup:
        why = suspicious_neutral(r)
        if why:
            print(f"  ! suspicious measurement {r['hex']} ({why}): {r.get('slug')} — add to color_overrides.json")

    config.FILAMENTS_JSON.write_text(json.dumps(dedup, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for r in dedup if r.get("rgb"))
    by_lib = {}
    for r in dedup:
        by_lib.setdefault(r.get("library", "cz"), 0)
        by_lib[r.get("library", "cz")] += 1
    print(f"→ {config.FILAMENTS_JSON}  ({ok}/{len(dedup)} with RGB)  by library: {by_lib}")

if __name__ == "__main__":
    main()
