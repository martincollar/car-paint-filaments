"""Prepare the recolor-preview assets of one car: a colour-neutral photo and (optionally) the mask.

The preview recolours the body in the browser (see HERO_JS in build_html.py), so every pixel of the
original paint that the mask misses stays visibly in the old colour: edges, specular rims, pink
reflections in the glass, orange side-markers. This tool removes the old paint colour from the
photo first (chroma -> 0, lightness kept), so whatever the mask misses ends up grey, not orange.

Usage:  python make_hero_assets.py [--car <name>]
Reads   cars/<car>/hero_assets.json (see below) and cars/<car>/sources/hero.jpg (the untouched original;
        never overwritten).
Writes  cars/<car>/sources/hero_neutral.jpg                 -> set "photo" of car.json's hero block to it
        cars/<car>/sources/hero_mask.png                    -> only with "mask": "chroma"

hero_assets.json (all coordinates are pixels of a photo `ref_width` wide, so they survive a larger
re-download of the same picture):
  ref_width     width the shapes below were measured on
  hue           Lab hue angle (degrees) at the centre of the paint colour to neutralise (orange 45, red 40)
  hue_reach     [full, zero] angular distance from `hue` where neutralising fades out (default [70, 100])
  chroma        [lo, hi] Lab chroma ramp of the neutralising weight (default [2, 8])
  mask          "chroma": derive the body mask from the paint's own chroma (soft alpha for free), or
                "keep": leave the existing hero_mask.png alone and neutralise only within `grow` px of it
  mask_chroma   [lo, hi] ramp of the mask alpha when mask is "chroma" (default [7, 22]); pastel paints need a
                lower ramp, e.g. [3, 10]
  lift          L* points added to the grey that is left where the old paint was (only with "mask": "chroma"); the
                recolour result stays the same, but the greyed "?" state of the preview gets lighter. Doppler's grey is
                L* ~77, Sakura's ~72
  roof_shape    optional single-channel PNG (white = roof), path relative to the car folder: two-tone cars. With "mask": "chroma" the
                roof part of the alpha goes to the mask's G channel instead of R. Only a hint: its largest blob is
                kept and grown by `roof_grow` px (default 6, must stay below the chrome gap
                to the body); `roof_extra` (shapes dict) adds parts the outline misses, e.g. the tip
  zones         optional extra paint areas of the car beyond body (R) and roof (G): {"<id>": {"channel": 2,
                "shape": <shapes dict>}}. The part of the body alpha inside the shape moves to that mask channel
                (B for channel 2), so the page can colour that area on its own (Doppler: "lower" = the body below the
                chrome line). Slots shown on the page come from `hero.zones` in car.json. Marks of that id
                (review_hero.py) force an area into the zone.
  grow          px (ref scale) around the existing mask in which "keep" mode neutralises (default 10), or
                "all" for the whole photo (right when nothing but paint and glass tint has that hue)
  keep_color    rects that stay in their colour (turn-signal lenses)
  glass         polygons: neutralised completely and never painted (windows, interior)
  never_paint   ellipses/rects that are neutralised but never painted (headlight lens)
Shapes: {"polygons": [[[x,y],..]], "rects": [[x0,y0,x1,y1]], "ellipses": [[x0,y0,x1,y1]]}

cars/<car>/hero_marks.json (written by review_hero.py; polygons or wand clicks {seed, tol} in pixels of hero.jpg itself,
a wand mark = the connected area of similar colour around the clicked pixel) is merged on top:
  never      never repainted (alpha 0, wins over everything)
  paint      always repainted as body (alpha 1)
  roof       always repainted as roof (alpha 1, G channel)
  <zone id>  always repainted as that zone (alpha 1, its channel) for every id in `zones`
  neutralise old paint colour removed here even where the chroma rule missed it
  keep       keeps its colour (neutralising and painting both off)
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import config

M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
Mi = np.linalg.inv(M)
WP = np.array([0.95047, 1, 1.08883])

def _lin(c):  return np.where(c / 255 > 0.04045, ((c / 255 + 0.055) / 1.055) ** 2.4, c / 255 / 12.92)
def _gam(c):  return np.clip(np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(np.maximum(c, 0), 1 / 2.4) - 0.055), 0, 1) * 255
def _f(t):    return np.where(t > 216 / 24389, np.cbrt(t), (24389 / 27 * t + 16) / 116)
def _finv(t): return np.where(t ** 3 > 216 / 24389, t ** 3, (116 * t - 16) / (24389 / 27))

def to_lab(rgb):
    xyz = _lin(rgb) @ M.T
    fx, fy, fz = (_f(xyz[..., i] / WP[i]) for i in range(3))
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], -1)

def to_rgb(lab):
    ly = (lab[..., 0] + 16) / 116
    xyz = np.stack([_finv(ly + lab[..., 1] / 500) * WP[0], _finv(ly), _finv(ly - lab[..., 2] / 200) * WP[2]], -1)
    return _gam(xyz @ Mi.T)

def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)

def shape_mask(size, shapes, k, blur):
    """Soft 0..1 mask of a shapes dict ({"polygons","rects","ellipses"}) given in ref-scale coordinates."""
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for poly in (shapes or {}).get("polygons", []):
        d.polygon([(x * k, y * k) for x, y in poly], fill=255)
    for r in (shapes or {}).get("rects", []):
        d.rectangle([v * k for v in r], fill=255)
    for e in (shapes or {}).get("ellipses", []):
        d.ellipse([v * k for v in e], fill=255)
    return np.array(m.filter(ImageFilter.GaussianBlur(blur * k))).astype(float) / 255

def wand_region(rgb, seed, tol):
    """Connected region around `seed` whose colour is within `tol` (RGB distance) of the seed pixel: the click-to-select
    tool of review_hero.py, so the user only has to point at an area instead of tracing it."""
    from scipy import ndimage
    x, y = int(round(seed[0])), int(round(seed[1]))
    lab_, _ = ndimage.label(((rgb - rgb[y, x]) ** 2).sum(axis=2) <= tol * tol)
    return lab_ == lab_[y, x] if lab_[y, x] else np.zeros(rgb.shape[:2], bool)

def load_marks(car, size, zone_ids=()):
    """{kind: soft 0..1 mask} from hero_marks.json (polygons or wand clicks in photo pixels); empty masks without a file."""
    path = config.car_dir(car) / "hero_marks.json"
    marks = json.loads(path.read_text(encoding="utf-8")).get("marks", []) if path.exists() else []
    rgb = None
    out = {}
    for kind in ("never", "paint", "roof", "neutralise", "keep") + tuple(zone_ids):
        m = Image.new("L", size, 0)
        d = ImageDraw.Draw(m)
        region = np.zeros(size[::-1], bool)
        for mk in marks:
            if mk.get("type") != kind:
                continue
            if mk.get("shape") == "wand":
                if rgb is None:
                    rgb = np.array(Image.open(config.car_sources(car) / "hero.jpg").convert("RGB")).astype(int)
                region |= wand_region(rgb, mk["seed"], mk.get("tol", 30))
            elif len(mk.get("points", [])) >= 3:
                d.polygon([tuple(pt) for pt in mk["points"]], fill=255)
        out[kind] = np.array(Image.fromarray(np.maximum(np.array(m), region * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.8))).astype(float) / 255
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    args = ap.parse_args()
    src_dir = config.car_sources(args.car)
    cfg = json.loads((config.car_dir(args.car) / "hero_assets.json").read_text(encoding="utf-8"))

    src = Image.open(src_dir / "hero.jpg").convert("RGB")
    k = src.size[0] / cfg["ref_width"]
    lab = to_lab(np.array(src).astype(float))
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    hue = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360
    dist = np.abs((hue - cfg["hue"] + 180) % 360 - 180)
    reach = cfg.get("hue_reach", [70, 100])
    band = 1 - smooth(dist, *reach)
    c_lo, c_hi = cfg.get("chroma", [2, 8])

    keep = shape_mask(src.size, {"rects": cfg.get("keep_color", [])}, k, 1.2)
    glass = shape_mask(src.size, cfg.get("glass"), k, 1.2)
    never = shape_mask(src.size, cfg.get("never_paint"), k, 1.2)
    zones = cfg.get("zones") or {}
    marks = load_marks(args.car, src.size, tuple(zones))
    keep = np.maximum(keep, marks["keep"])

    weight = smooth(chroma, c_lo, c_hi) * band
    if cfg.get("mask") == "keep" and cfg.get("grow", 10) != "all":
        mk = np.array(Image.open(src_dir / "hero_mask.png").convert("RGB")).astype(float).max(axis=2) / 255
        near = Image.fromarray((mk > 0.05).astype("uint8") * 255).filter(ImageFilter.MaxFilter(int(cfg.get("grow", 10) * k) // 2 * 2 + 1))
        weight *= np.array(near).astype(float) / 255
    weight = np.maximum(np.maximum(weight, glass), marks["neutralise"])   # glass and interior lose all colour
    weight *= (1 - keep)
    neutral = lab.copy()
    neutral[..., 1] *= 1 - weight
    neutral[..., 2] *= 1 - weight
    Image.fromarray(to_rgb(neutral).astype("uint8")).save(src_dir / "hero_neutral.jpg", quality=95)
    print(f"[{args.car}] neutralised {(weight > 0.5).mean():.1%} of the photo → hero_neutral.jpg")

    if cfg.get("mask") == "chroma":
        m_lo, m_hi = cfg.get("mask_chroma", [7, 22])
        ex = np.array(Image.fromarray((np.maximum(glass, never) * 255).astype("uint8"))
                      .filter(ImageFilter.MinFilter(int(9 * k) // 2 * 2 + 1)).filter(ImageFilter.GaussianBlur(k))).astype(float) / 255
        # paint only warm paint hues; the pink of reflections in the glass never counts as body
        warm = 1 - smooth(np.abs((hue - cfg["hue"] + 180) % 360 - 180), 45, 75)
        alpha = smooth(chroma, m_lo, m_hi) * warm * (1 - ex) * (1 - keep)
        a = np.array(Image.fromarray((alpha * 255).astype("uint8"))
                     .filter(ImageFilter.MaxFilter(int(3 * k) // 2 * 2 + 1)).filter(ImageFilter.GaussianBlur(0.6 * k)))
        a = a.astype(float) / 255
        roof = np.zeros_like(a)
        if cfg.get("roof_shape"):
            # the roof outline is only a hint: keep its largest blob (drops slivers on chrome trim), add `roof_extra`
            # shapes where it falls short (the tip), grow it a little so it covers the soft edge of the alpha. The
            # growth must stay below the chrome gap to the body or a green line appears on the body's top edge.
            from scipy import ndimage
            hint = np.array(Image.open(src_dir.parent / cfg["roof_shape"]).convert("L").resize(src.size)) > 127
            lab_, n = ndimage.label(hint)
            if n:
                hint = lab_ == (1 + int(np.argmax(ndimage.sum(hint, lab_, range(1, n + 1)))))
            hint |= shape_mask(src.size, cfg.get("roof_extra"), k, 0) > 0.5
            hint = ndimage.binary_dilation(hint, iterations=max(1, int(cfg.get("roof_grow", 6) * k)))
            roof = np.array(Image.fromarray((hint * 255).astype("uint8")).filter(ImageFilter.GaussianBlur(k))).astype(float) / 255
        body_a, roof_a = a * (1 - roof), a * roof
        # hand marks win over the chroma rule: forced paint first, then keep / never
        # a paint mark takes its area away from the other channel, so a pixel never ends up half body, half roof
        body_a = np.maximum(body_a * (1 - marks["roof"]), marks["paint"]) * (1 - marks["keep"]) * (1 - marks["never"])
        roof_a = np.maximum(roof_a * (1 - marks["paint"]), marks["roof"]) * (1 - marks["keep"]) * (1 - marks["never"])
        out = np.zeros(a.shape + (3,), "uint8")
        for zid, z in zones.items():
            # an extra zone takes its share of the body alpha (the shape is only a hint, soft edge), marks of that id force it;
            # what it takes is removed from the body channel, so a pixel is never half body, half zone
            hint = shape_mask(src.size, z.get("shape"), k, 1.2)
            forced = marks[zid] * (1 - marks["keep"]) * (1 - marks["never"])
            zone_a = np.maximum(body_a * hint, forced)
            body_a = body_a * (1 - hint) * (1 - forced)
            out[..., z["channel"]] = (zone_a * 255).astype("uint8")
        out[..., 0] = (body_a * 255).astype("uint8")
        out[..., 1] = (roof_a * 255).astype("uint8")
        Image.fromarray(out).save(src_dir / "hero_mask.png")
        print(f"[{args.car}] body mask from chroma → hero_mask.png")
        if cfg.get("lift"):
            # lighten the grey that is left of the old paint (the greyed "?" state of the preview). The recolour only uses the
            # shading around the body mean, so an even lift leaves the recoloured car as it was; a soft knee keeps the
            # brightest highlights from clipping
            cov = out.max(axis=2) / 255
            lifted = neutral[..., 0] + cfg["lift"]
            lifted = np.where(lifted > 92, 92 + (lifted - 92) * 0.35, lifted)
            neutral[..., 0] = neutral[..., 0] * (1 - cov) + lifted * cov
            Image.fromarray(to_rgb(neutral).astype("uint8")).save(src_dir / "hero_neutral.jpg", quality=95)
            print(f"[{args.car}] painted grey lifted by {cfg['lift']} L* → hero_neutral.jpg")

if __name__ == "__main__":
    main()
