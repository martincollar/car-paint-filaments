"""Build the inline hero photo + paint mask for the live recolor preview.

Reads `hero` from `cars/<car>/car.json`:
    {"photo": "sources/hero.jpg", "mask": "sources/hero_mask.png", "roof": "#ffffff",
     "credit": "...", "credit_url": "..."}
The mask is an RGB PNG, one paint area per channel (0-255 coverage, soft edges): R = body, G = roof, B = a third area.
`zones` (optional) names the areas the page lets the user colour on their own ("slots"):
    "zones": [{"id": "upper", "label": "Upper body", "channels": [0]},
              {"id": "lower", "label": "Lower body", "channels": [2]},
              {"id": "roof",  "label": "Roof",       "channels": [1], "fixed": true}]
`channels` index the mask's R/G/B; `fixed` keeps the area in the colour `roof` until the user colours it by hand.
Optional per zone: `dl` (shift of the painted lightness, L* points) and `contrast` (factor on the photo's shading inside the zone,
1 = as photographed), for an area that reads too dark or too flat (Doppler's roof).
A zone without `label` is never offered as a slot of its own and just follows every pick. Without `zones` the
car has body (R) and roof (G): the roof is `roof` when set, otherwise it follows the body, and the page offers one colour.
`roof` is the fixed roof colour; omit it to give the roof the body colour.

`tone` ({"dl": L* shift of the target lightness, "contrast": factor on the body shading}) is taken from
`cars/<car>/hero_assets.json`; set with the calibration page of review_hero.py.

Produces `cars/<car>/data/hero.json` ({photo, mask, roof, tone, credit, credit_url}) and
does nothing for a car without `hero`.

Usage:
    python prepare_hero.py [--car <name>]
"""
import argparse, base64, io, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image
from color_tools import _load
import config

MAX_W = 1000

def _resize(img, w):
    h = round(img.height * w / img.width)
    return img.resize((w, h), Image.LANCZOS)

def photo_uri(img, quality=78):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

def mask_uri(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    args = ap.parse_args()

    hero = config.car_meta(args.car).get("hero")
    out = config.car_data(args.car) / "hero.json"
    if not hero:
        out.unlink(missing_ok=True)
        print(f"[{args.car}] no hero in car.json, skipped")
        return

    base = config.car_dir(args.car)
    photo = Image.fromarray(_load(base / hero["photo"]))
    mask = Image.open(base / hero["mask"]).convert("RGB")
    if mask.size != photo.size:
        sys.exit(f"mask {mask.size} and photo {photo.size} differ in size")

    assets = base / "hero_assets.json"
    tone = json.loads(assets.read_text(encoding="utf-8")).get("tone") if assets.exists() else None
    zones = hero.get("zones") or ([{"id": "body", "channels": [0]},
                                   {"id": "roof", "channels": [1], **({"fixed": True} if hero.get("roof") else {})}])
    for z in zones:
        z.setdefault("label", "")
    w = min(MAX_W, photo.width)
    data = {"photo": photo_uri(_resize(photo, w)),
            "mask": mask_uri(_resize(mask, w)),
            "roof": hero.get("roof"),
            "zones": zones,
            "tone": tone,
            "credit": hero.get("credit", ""),
            "credit_url": hero.get("credit_url", "")}
    config.write_json(out, data, indent=None)
    print(f"[{args.car}] hero {w}px → {out} ({out.stat().st_size/1024:.1f} KB)")

if __name__ == "__main__":
    main()
