"""Tighten a car's recolor mask (`hero_mask.png`, R = body paint) so it only covers paint-coloured pixels.

The hand-made mask also catches dark interior seen through the windows and shaded chrome edges, which turn the
wrong colour in the recolor preview. Here the body channel is cut down to pixels whose hue matches the paint
(median hue of the mask interior) and that still carry some of its chroma. The roof channel is kept as it is.

Writes `cars/<car>/sources/cut_work/hero_mask_refined.png` and a before/after preview; copy it over
`cars/<car>/sources/hero_mask.png` (then run prepare_hero.py) to use it.

Usage:
    python refine_paint_mask.py --car doppler
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from PIL import Image, ImageFilter
import config

_M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
_WP = np.array([0.95047, 1.0, 1.08883])


def lab(rgb):
    c = rgb.astype(float) / 255
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ _M.T / _WP
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def paint_keep(photo, mask, hue_tol=38.0, min_chroma=0.35):
    """soft 0..1 map: how paint-like each pixel is (hue of the mask interior, enough chroma)"""
    L = lab(np.asarray(photo))
    body = np.asarray(mask)[..., 0].astype(float) / 255
    core = body > 0.9
    a, b = L[..., 1], L[..., 2]
    chroma, hue = np.hypot(a, b), np.degrees(np.arctan2(b, a))
    c0 = np.median(chroma[core])
    h0 = np.degrees(np.arctan2(np.median(b[core]), np.median(a[core])))
    dh = np.abs((hue - h0 + 180) % 360 - 180)
    keep = (dh <= hue_tol) & (chroma >= min_chroma * c0)
    # heal specular highlights and tiny gaps inside the paint, but not the big window-sized holes
    k = Image.fromarray(keep.astype("uint8") * 255)
    k = k.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7)).filter(ImageFilter.GaussianBlur(1.2))
    return np.asarray(k).astype(float) / 255


def refine(photo, mask, hue_tol=38.0, min_chroma=0.35):
    body = np.asarray(mask)[..., 0].astype(float) / 255
    soft = paint_keep(photo, mask, hue_tol, min_chroma)
    out = np.asarray(mask).copy()
    out[..., 0] = (body * soft * 255).astype("uint8")
    return Image.fromarray(out), body, body * soft


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    ap.add_argument("--hue-tol", type=float, default=38.0)
    ap.add_argument("--min-chroma", type=float, default=0.35)
    args = ap.parse_args()
    src = config.car_sources(args.car)
    photo = Image.open(src / "hero.jpg").convert("RGB")
    mask = Image.open(src / "hero_mask.png").convert("RGB")
    out, before, after = refine(photo, mask, args.hue_tol, args.min_chroma)
    work = src / "cut_work"
    work.mkdir(exist_ok=True)
    out.save(work / "hero_mask_refined.png")
    p = np.asarray(photo).astype(float)
    for name, m in (("pred", before), ("po", after)):
        ov = p * (1 - 0.7 * m[..., None]) + np.array([255, 0, 255]) * 0.7 * m[..., None]
        Image.fromarray(ov.clip(0, 255).astype("uint8")).save(work / f"maska_laku_{name}.png")
    print(f"body mask pixels {int((before > .5).sum())} -> {int((after > .5).sum())}; wrote {work}/hero_mask_refined.png")


if __name__ == "__main__":
    main()
