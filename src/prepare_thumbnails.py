"""Build inline base64 thumbnails for the HTML.

Produces `cars/<car>/data/thumbnails_<library>.json`.

Usage:
    python prepare_thumbnails.py [--car <name>] [--library cz|intl]
"""
import argparse, json, sys, base64, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from collections import deque
from PIL import Image, ImageFilter
import config

SEARCH_X, SEARCH_Y = 120, 40   # search window around the swatch centre
COLOR_TOL = 30                 # max RGB distance from the swatch colour
INSET = 4                      # px trimmed off the swatch edge (scan blur)

def swatch_crop(im, cx, cy, rgb, box_w, box_h):
    """Crop just the swatch: flood-fill from (cx, cy) over pixels close to its
    colour, take the bounding box and trim the blurry edge. Falls back to the
    measurement box when the fill is implausibly small or leaks out of the window."""
    W, H = im.size
    l, r = max(0, cx - SEARCH_X), min(W, cx + SEARCH_X)
    t, b = max(0, cy - SEARCH_Y), min(H, cy + SEARCH_Y)
    win = np.asarray(im.crop((l, t, r, b)).filter(ImageFilter.MedianFilter(3)), dtype=np.int16)
    close = np.abs(win - np.array(rgb, dtype=np.int16)).sum(axis=2) <= COLOR_TOL * 1.7
    h, w = close.shape
    sy, sx = cy - t, cx - l
    seen = np.zeros_like(close)
    q = deque()
    if close[sy, sx]:
        seen[sy, sx] = True; q.append((sy, sx))
    while q:
        y, x = q.popleft()
        for ny, nx in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
            if 0 <= ny < h and 0 <= nx < w and close[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True; q.append((ny, nx))
    ys, xs = np.nonzero(seen)
    fallback = (max(0, cx - box_w//2), max(0, cy - box_h//2),
                min(W, cx + box_w//2), min(H, cy + box_h//2))
    if len(ys) == 0:
        return im.crop(fallback), False
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    leaks = x0 == 0 or y0 == 0 or x1 == w or y1 == h
    if leaks or (x1 - x0) < box_w or (y1 - y0) < box_h:
        return im.crop(fallback), False
    x0 += INSET; x1 -= INSET; y0 += INSET; y1 -= INSET
    return im.crop((l + x0, t + y0, l + x1, t + y1)), True

def to_b64_jpg(img, max_dim=120, quality=72):
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
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
    ap.add_argument("--library", default="cz", choices=["cz", "intl"])
    args = ap.parse_args()

    car_data    = config.car_data(args.car)
    car_sources = config.car_sources(args.car)
    colors    = json.loads((car_data / "car_colors.json").read_text(encoding="utf-8"))
    all_fil   = json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8"))
    filaments = [f for f in all_fil if f.get("library", "cz") == args.library]

    # Car swatches cropped from the cards
    layout = json.loads((config.car_dir(args.car) / "card_layout.json").read_text(encoding="utf-8"))
    box_w, box_h = layout.get("box_width", 120), layout.get("box_height", 35)
    car_thumb, fell_back = {}, []
    for h in colors:
        cx, cy = h["source_pos"]
        path = car_sources / Path(h["source_file"]).name
        im = Image.open(path).convert("RGB")
        W, H = im.size
        crop, ok = swatch_crop(im, cx, cy, h["rgb"], box_w, box_h)
        if not ok: fell_back.append(h["name"])
        car_thumb[f"{h['year']}-{h['name']}"] = to_b64_jpg(crop, max_dim=200, quality=78)

    if fell_back: print(f"swatch outline not found, used measurement box: {fell_back}")

    # Filament thumbs for only this library
    fil_thumb = {}
    for f in filaments:
        if not f.get("local_image"): continue
        path = config.FILAMENTS_SOURCES / f["local_image"]
        try:
            im = Image.open(path)
            fil_thumb[f["slug"]] = to_b64_jpg(im, max_dim=100, quality=70)
        except Exception as e:
            print(f"thumb fail {f['slug']}: {e}")

    out = car_data / f"thumbnails_{args.library}.json"
    out.write_text(json.dumps({"car": car_thumb, "filaments": fil_thumb}), encoding="utf-8")
    total_kb = (sum(len(v) for v in car_thumb.values())
                + sum(len(v) for v in fil_thumb.values())) / 1024
    print(f"[{args.car}/{args.library}] {len(car_thumb)} car + {len(fil_thumb)} filament thumbs → {out} ({total_kb:.1f} KB)")

if __name__ == "__main__":
    main()
