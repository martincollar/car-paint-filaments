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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    car_data = config.car_data(args.car)
    colors   = json.loads((car_data / "car_colors.json").read_text(encoding="utf-8"))
    all_fil  = [f for f in json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8")) if f.get("rgb")]

    result = {}
    for region in shoplib.region_labels():
        filaments = in_region(all_fil, region)
        pla  = [f for f in filaments if f["material"] in config.PLA_MATERIALS]
        petg = [f for f in filaments if f["material"] in config.PETG_MATERIALS]
        asa  = [f for f in filaments if f["material"] in config.ASA_MATERIALS]
        print(f"[{args.car}/{region}] {len(colors)} car colors × {len(pla)} PLA + {len(petg)} PETG + {len(asa)} ASA")
        pla_lab  = rgb_to_lab([f["rgb"] for f in pla])  if pla  else None
        petg_lab = rgb_to_lab([f["rgb"] for f in petg]) if petg else None
        asa_lab  = rgb_to_lab([f["rgb"] for f in asa])  if asa  else None
        matches = []
        for h in colors:
            rec = dict(h)
            rec["pla"]   = topk(h["rgb"], pla,  k=args.k, pool_lab=pla_lab)
            rec["petg"]  = topk(h["rgb"], petg, k=args.k, pool_lab=petg_lab)
            rec["asa"]   = topk(h["rgb"], asa,  k=args.k, pool_lab=asa_lab)
            matches.append(rec)
        result[region] = matches

    out = car_data / "matches.json"
    config.write_json(out, result)
    print(f"→ {out}")

if __name__ == "__main__":
    main()
