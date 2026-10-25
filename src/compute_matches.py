"""For each car color, find top-K PLA and PETG filament candidates by ΔE2000.

Writes `cars/<car>/data/matches.json` as {region: [color + pla/petg candidates]}, one
match set per region in shops/_defaults.yaml; a filament is a candidate in every region
its shop lists.

Usage:
    python compute_matches.py [--car <name>] [--k 5]
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from color_tools import delta_e_2000_many, rgb_to_lab
import config, shoplib

# Neon filaments rank as if this far away (the shown ΔE stays real): on a car they only look
# right when the paint itself is neon, and their photos measure darker than they are, so plain
# ΔE flatters them. Not applied to a paint whose Lab chroma is at least NEON_PAINT_CHROMA.
NEON_PENALTY = 8.0
NEON_PAINT_CHROMA = 85.0

def topk(target_rgb, pool, k=5, pool_lab=None):
    """The k filaments of `pool` closest to `target_rgb`; ties keep pool order.
    Pass `pool_lab` (rgb_to_lab of every pool rgb) to convert the pool only once."""
    if not pool:
        return []
    if pool_lab is None:
        pool_lab = rgb_to_lab([f["rgb"] for f in pool])
    target_lab = rgb_to_lab(target_rgb)
    dE = delta_e_2000_many(target_lab, pool_lab)
    rank = dE
    if np.hypot(target_lab[1], target_lab[2]) < NEON_PAINT_CHROMA:
        rank = dE + NEON_PENALTY * np.array([bool(f.get("neon")) for f in pool])
    order = np.argsort(rank, kind="stable")[:k]
    return [{"delta_e": round(float(dE[i]), 2), **pool[i]} for i in order]

def in_region(filaments, region):
    return [f for f in filaments if region in (f.get("regions") or [])]

def allowed_finishes(meta):
    """The finishes a car shows by default: `filter_defaults` in car.json ({finish: bool}; missing = off)."""
    on = meta.get("filter_defaults") or {}
    return frozenset(n for n in shoplib.finish_names() if on.get(n))

def finish_key(allowed):
    """Stable name of a set of allowed finishes, in toggle order: '-' = plain only, 'glitter+matt', ..."""
    return "+".join(n for n in shoplib.finish_names() if n in allowed) or "-"

def all_finish_sets():
    """Every subset of the finishes (each one a state of the page's toggles), plain-only first."""
    names = shoplib.finish_names()
    return [frozenset(n for i, n in enumerate(names) if m >> i & 1) for m in range(1 << len(names))]

def without_finishes(filaments, allowed):
    """Drop the filaments that have a finish which is not allowed."""
    return [f for f in filaments if not (set(f.get("finish") or ()) - allowed)]

def match_colors(colors, filaments, region, allowed, k=5):
    """[color + pla/petg/asa top-k] for one region with only the `allowed` finishes in the pool."""
    pool_all = without_finishes(in_region(filaments, region), allowed)
    pools = {m: [f for f in pool_all if f["material"] in mats]
             for m, mats in (("pla", config.PLA_MATERIALS), ("petg", config.PETG_MATERIALS), ("asa", config.ASA_MATERIALS))}
    labs = {m: rgb_to_lab([f["rgb"] for f in p]) if p else None for m, p in pools.items()}
    out = []
    for h in colors:
        rec = dict(h)
        for m, p in pools.items():
            rec[m] = topk(h["rgb"], p, k=k, pool_lab=labs[m])
        out.append(rec)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    car_data = config.car_data(args.car)
    colors   = json.loads((car_data / "car_colors.json").read_text(encoding="utf-8"))
    all_fil  = [f for f in json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8")) if f.get("rgb")]
    allowed  = allowed_finishes(config.car_meta(args.car))

    # matches.json holds the car's default finish set (what the root-page tiles use); build_html.py
    # calls match_colors() itself for the other states of the finish toggles.
    result = {}
    for region in shoplib.region_labels():
        result[region] = match_colors(colors, all_fil, region, allowed, args.k)
        print(f"[{args.car}/{region}] {len(colors)} car colors, finishes allowed: {finish_key(allowed)}")

    out = car_data / "matches.json"
    config.write_json(out, result)
    print(f"→ {out}")

if __name__ == "__main__":
    main()
