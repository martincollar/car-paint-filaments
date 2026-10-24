"""For each car color, find top-K PLA and PETG filament candidates by ΔE2000.

Writes `cars/<car>/data/matches_<library>.json`.

Usage:
    python compute_matches.py [--car <name>] [--library cz|intl] [--k 5]
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from color_tools import delta_e_2000_many, rgb_to_lab
import config

def topk(target_rgb, pool, k=5, pool_lab=None):
    """The k filaments of `pool` closest to `target_rgb`; ties keep pool order.
    Pass `pool_lab` (rgb_to_lab of every pool rgb) to convert the pool only once."""
    if not pool:
        return []
    if pool_lab is None:
        pool_lab = rgb_to_lab([f["rgb"] for f in pool])
    dE = delta_e_2000_many(rgb_to_lab(target_rgb), pool_lab)
    order = np.argsort(dE, kind="stable")[:k]
    return [{"delta_e": round(float(dE[i]), 2), **pool[i]} for i in order]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    ap.add_argument("--library", default="cz", choices=["cz", "intl"])
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    car_data = config.car_data(args.car)
    colors   = json.loads((car_data / "car_colors.json").read_text(encoding="utf-8"))
    all_fil  = [f for f in json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8")) if f.get("rgb")]
    filaments = [f for f in all_fil if f.get("library", "cz") == args.library]

    pla  = [f for f in filaments if f["material"] in config.PLA_MATERIALS]
    petg = [f for f in filaments if f["material"] in config.PETG_MATERIALS]
    print(f"[{args.car}/{args.library}] {len(colors)} car colors × {len(pla)} PLA + {len(petg)} PETG")
    pla_lab  = rgb_to_lab([f["rgb"] for f in pla])  if pla  else None
    petg_lab = rgb_to_lab([f["rgb"] for f in petg]) if petg else None

    matches = []
    for h in colors:
        rec = dict(h)
        rec["pla"]   = topk(h["rgb"], pla,  k=args.k, pool_lab=pla_lab)
        rec["petg"]  = topk(h["rgb"], petg, k=args.k, pool_lab=petg_lab)
        matches.append(rec)

    out = car_data / f"matches_{args.library}.json"
    config.write_json(out, matches)
    print(f"→ {out}")

if __name__ == "__main__":
    main()
