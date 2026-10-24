"""For each car color, find top-K PLA and PETG filament candidates by ΔE2000.

Writes `cars/<car>/data/matches_<library>.json`.

Usage:
    python compute_matches.py [--car <name>] [--library cz|intl] [--k 5]
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from color_tools import delta_e_2000
import config

def topk(target_rgb, pool, k=5):
    scored = [(delta_e_2000(target_rgb, f["rgb"]), f) for f in pool]
    scored.sort(key=lambda x: x[0])
    return [{"delta_e": round(dE, 2), **f} for dE, f in scored[:k]]

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

    pla  = [f for f in filaments if f["material"] in ("PLA", "PLA+")]
    petg = [f for f in filaments if f["material"] == "PETG"]
    print(f"[{args.car}/{args.library}] {len(colors)} car colors × {len(pla)} PLA + {len(petg)} PETG")

    matches = []
    for h in colors:
        rec = dict(h)
        rec["pla"]   = topk(h["rgb"], pla, k=args.k)
        rec["petg"]  = topk(h["rgb"], petg, k=args.k)
        matches.append(rec)

    out = car_data / f"matches_{args.library}.json"
    out.write_text(json.dumps(matches, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"→ {out}")

if __name__ == "__main__":
    main()
