"""Build inline base64 filament thumbnails for the HTML.

Produces `cars/<car>/data/thumbnails.json` ({"filaments": {slug: data-URI}}).

Usage:
    python prepare_thumbnails.py [--car <name>]
"""
import argparse, json, sys, base64, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from PIL import Image
from color_tools import _load
import config

def to_b64_jpg(img, max_dim=120, quality=72):
    """JPEG data URI of a PIL image. Load photos with `Image.fromarray(_load(path))`
    so transparent PNGs are composited over white first."""
    img = img.convert("RGB")
    w, h = img.size
    sc = max_dim / max(w, h)
    if sc < 1:
        img = img.resize((int(w*sc), int(h*sc)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    args = ap.parse_args()

    car_data  = config.car_data(args.car)
    filaments = json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8"))

    fil_thumb = {}
    for f in filaments:
        if not f.get("local_image"): continue
        path = config.FILAMENTS_SOURCES / f["local_image"]
        try:
            fil_thumb[f["slug"]] = to_b64_jpg(Image.fromarray(_load(path)), max_dim=100, quality=70)
        except Exception as e:
            print(f"thumb fail {f['slug']}: {e}")

    out = car_data / "thumbnails.json"
    config.write_json(out, {"filaments": fil_thumb}, indent=None)
    total_kb = sum(len(v) for v in fil_thumb.values()) / 1024
    print(f"[{args.car}] {len(fil_thumb)} filament thumbs → {out} ({total_kb:.1f} KB)")

if __name__ == "__main__":
    main()
