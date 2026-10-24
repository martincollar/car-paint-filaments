"""Measure car paint colors from scanned color cards.

Reads `cars/<car>/card_layout.json` which lists each card image and the
per-swatch pixel coordinates. Writes `cars/<car>/data/car_colors.json`.

Usage:
    python measure_car.py [--car <name>]

card_layout.json shape:
{
  "box_width": 120, "box_height": 35,
  "source_url_template": "https://.../pages/{year}-<car>",
  "cards": [
    {
      "card_file": "1952-hudson-pg01.jpg",
      "box_width": 60, "box_height": 24,      (optional per-card override)
      "swatches": [
        {"cx":185,"cy":87,"name":"Gulf Green","year":1952,"car_code":"Q-115","paint_ref":"41206","poly":false},
        ...
      ]
    },
    ...
  ]
}
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from color_tools import _load, rgb_to_hex
import config

def measure_region(path, cx, cy, w, h):
    im = _load(path)
    H, W, _ = im.shape
    l = max(0, cx - w//2); r = min(W, cx + w//2)
    t = max(0, cy - h//2); b = min(H, cy + h//2)
    patch = im[t:b, l:r]
    med = np.median(patch.reshape(-1, 3), axis=0)
    return tuple(int(round(x)) for x in med)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    args = ap.parse_args()

    cdir     = config.car_dir(args.car)
    sources  = config.car_sources(args.car)
    data_dir = config.car_data(args.car)
    data_dir.mkdir(parents=True, exist_ok=True)

    layout = json.loads((cdir / "card_layout.json").read_text(encoding="utf-8"))
    bw = layout.get("box_width", 120)
    bh = layout.get("box_height", 35)
    url_tpl = layout.get("source_url_template", "")

    records = []
    for card in layout["cards"]:
        card_file = card["card_file"]
        year_hint = None
        # Pull year prefix out of filename if swatch doesn't supply one explicitly
        for part in card_file.split("-"):
            if part.isdigit() and len(part) == 4:
                year_hint = int(part); break
        # A card with smaller chips can override the layout-wide box size.
        cbw = card.get("box_width", bw)
        cbh = card.get("box_height", bh)
        for sw in card["swatches"]:
            year = sw.get("year") or year_hint
            rgb = measure_region(sources / card_file, sw["cx"], sw["cy"], cbw, cbh)
            records.append({
                "name":        sw["name"],
                "year":        year,
                "car_code":    sw.get("car_code", ""),
                "paint_ref":   sw.get("paint_ref", ""),
                "rgb":         list(rgb),
                "hex":         rgb_to_hex(rgb),
                "poly":        bool(sw.get("poly")),
                "source_url":  url_tpl.format(year=year) if (year and url_tpl) else "",
                "source_file": f"sources/{card_file}",
                "source_pos":  [sw["cx"], sw["cy"]],
                "confidence":  "measured_from_card",
            })

    out = data_dir / "car_colors.json"
    config.write_json(out, records)
    print(f"[{args.car}] {len(records)} swatches measured → {out}")

if __name__ == "__main__":
    main()
