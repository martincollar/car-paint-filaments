"""Tighten the recolor mask (`hero_mask.png`, R = body paint) with SAM (Segment Anything, through rembg).

Two modes, same prompts (positive points on the paint, negative ones on chrome, glass/interior, tyres, roof, all
taken from the existing mask):
  zone  (default) SAM, a paint-hue test and a darkness test trim the existing body mask, but only in a band around
        the windows, where the dark interior seen through the glass leaks into the mask. Elsewhere the existing mask
        is kept: SAM drops dark or glossy paint (Torq's shaded door, Doppler's door-seam reflections).
  cells (experiment) SAM prompted paint cell by cell, union of the cells as the new mask. Tried on both cars: it leaks
        onto tyres, glass and bumpers and is worse than the existing mask. Kept only to document that.
The roof channel (G) is kept.

Needs `pip install "rembg[cpu]"`; the SAM model (vit_b) downloads into ~/.rembg on first use.
Writes `cars/<car>/sources/cut_work/hero_mask_sam.png` + previews (green = positive points, yellow = negative);
copy it over `hero_mask.png` (then `prepare_hero.py`) to use it.

Usage:
    python sam_paint_mask.py --car doppler [--cells 16] [--neg 40]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from PIL import Image, ImageFilter
import config

INPUT_SIZE = (684, 1024)      # what rembg's SAM export expects


def farthest_points(mask, n, first=None):
    """n points of `mask` (bool array) spread out by farthest-point sampling, as [(x, y)]"""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return []
    step = max(1, len(xs) // 8000)
    pts = np.stack([xs[::step], ys[::step]], 1).astype(float)
    start = pts[np.argmin(np.hypot(*(pts - np.median(pts, 0)).T))] if first is None else np.array(first, float)
    chosen, d = [start], np.hypot(*(pts - start).T)
    for _ in range(n - 1):
        nxt = pts[np.argmax(d)]
        chosen.append(nxt)
        d = np.minimum(d, np.hypot(*(pts - nxt).T))
    return [(int(x), int(y)) for x, y in chosen]


def embed(session, img):
    """encode the photo once: (image embedding, original size, transform matrix)"""
    from rembg.sessions.sam import warp_affine
    cv = np.array(img.convert("RGB"))
    h, w = cv.shape[:2]
    scale = min(INPUT_SIZE[1] / w, INPUT_SIZE[0] / h)
    mat = np.array([[scale, 0, 0], [0, scale, 0], [0, 0, 1]])
    cv = warp_affine(cv, mat[:2], INPUT_SIZE)
    out = session.encoder.run(None, {session.encoder.get_inputs()[0].name: cv.astype(np.float32)})
    return out[0], (h, w), mat


def decode(session, emb, points, labels):
    """best SAM mask (bool, original size) for the given points (x, y in photo pixels) and labels (1 / 0)"""
    from rembg.sessions.sam import apply_coords, transform_masks
    image_embedding, original_size, mat = emb
    pts = np.concatenate([np.array(points, float), np.array([[0.0, 0.0]])], 0)[None]
    lab = np.concatenate([np.array(labels), np.array([-1])])[None].astype(np.float32)
    coord = apply_coords(pts, INPUT_SIZE, 1024).astype(np.float32)
    coord = np.concatenate([coord, np.ones((1, coord.shape[1], 1), np.float32)], 2)
    coord = np.matmul(coord, mat.T)[:, :, :2].astype(np.float32)
    masks, iou, _ = session.decoder.run(None, {
        "image_embeddings": image_embedding, "point_coords": coord, "point_labels": lab,
        "mask_input": np.zeros((1, 1, 256, 256), np.float32), "has_mask_input": np.zeros(1, np.float32),
        "orig_im_size": np.array(INPUT_SIZE, np.float32)})
    masks = transform_masks(masks, original_size, np.linalg.inv(mat))
    return masks[0, int(np.argmax(iou[0]))] > 0.0


def window_zone(photo, cut, radius=41):
    """float 0..1: a band around the pale glass patches in the upper half of the car"""
    from scipy.ndimage import binary_fill_holes
    a = np.asarray(photo).astype(int)
    mn, rng = a.min(2), a.max(2) - a.min(2)
    h, w = cut.shape
    rows = np.arange(h)[:, None]
    half = Image.fromarray(((cut > 0.5).astype("uint8") * 255)).resize((w // 2, h // 2)).filter(ImageFilter.MaxFilter(41)).filter(ImageFilter.MinFilter(41))
    car = binary_fill_holes(np.asarray(half.resize((w, h))) > 127)             # silhouette with the (cleared) glass filled in
    ys = np.where(car.any(1))[0]
    upper = rows < ys[0] + 0.52 * (ys[-1] - ys[0])
    seeds = (mn >= 200) & (rng < 14) & car & upper
    im = Image.fromarray(seeds.astype("uint8") * 255).filter(ImageFilter.MinFilter(15)).filter(ImageFilter.MaxFilter(radius))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(6))).astype(float) / 255


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    ap.add_argument("--mode", choices=("zone", "cells"), default="zone")
    ap.add_argument("--cells", type=int, default=16, help="paint cells, each prompted separately")
    ap.add_argument("--per-cell", type=int, default=2, help="positive points per cell")
    ap.add_argument("--neg", type=int, default=40, help="negative points (not paint)")
    args = ap.parse_args()
    from rembg import new_session
    from scipy.ndimage import distance_transform_edt

    src = config.car_sources(args.car)
    photo = Image.open(src / "hero.jpg").convert("RGB")
    mask = np.asarray(Image.open(src / "hero_mask.png").convert("RGB")).astype(float) / 255
    cut_path = src / "hero_cut.png"
    cut = np.asarray(Image.open(cut_path).convert("L")).astype(float) / 255 if cut_path.exists() else np.ones(mask.shape[:2])
    body, roof = mask[..., 0], mask[..., 1]

    # --- prompts, all taken from the existing mask
    core = distance_transform_edt(body > 0.95) > 10
    seeds = farthest_points(core, args.cells)
    ys, xs = np.nonzero(core)
    sx, sy = np.array([s[0] for s in seeds]), np.array([s[1] for s in seeds])
    owner = np.zeros(len(xs), int)
    for a in range(0, len(xs), 50000):
        owner[a:a + 50000] = np.argmin((xs[a:a + 50000, None] - sx) ** 2 + (ys[a:a + 50000, None] - sy) ** 2, 1)
    cells = []
    for i, s in enumerate(seeds):
        cell = np.zeros(core.shape, bool)
        cell[ys[owner == i], xs[owner == i]] = True
        cells.append(farthest_points(cell, args.per_cell, first=s))
    not_paint = (cut > 0.5) & (body < 0.05) & (distance_transform_edt(~(body > 0.3)) > 5)
    neg = farthest_points(not_paint, args.neg)
    neg += farthest_points(roof > 0.9, 4) if (roof > 0.9).any() else []

    # --- SAM: encode once, decode per cell
    session = new_session("sam")
    emb = embed(session, photo)
    if args.mode == "cells":
        union = np.zeros(core.shape, bool)
        for pts in cells:
            union |= decode(session, emb, pts + neg, [1] * len(pts) + [0] * len(neg))
        soft = np.asarray(Image.fromarray(union.astype("uint8") * 255).filter(ImageFilter.GaussianBlur(1.2))).astype(float) / 255
        near = np.asarray(Image.fromarray(union.astype("uint8") * 255).filter(ImageFilter.MaxFilter(7))) > 127
        new = np.maximum(soft, body * near)
    else:
        from refine_paint_mask import paint_keep, lab
        pos = [p for pts in cells[:10] for p in pts[:1]]
        union = decode(session, emb, pos + neg, [1] * len(pos) + [0] * len(neg))
        grown = Image.fromarray(union.astype("uint8") * 255).filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(2.0))
        both = np.asarray(grown).astype(float) / 255 * paint_keep(photo, (mask * 255).astype("uint8"))   # SAM and the hue test
        L = lab(np.asarray(photo))[..., 0]
        dark = L < 0.5 * np.median(L[body > 0.9])                                # dark interior behind the glass is not paint
        both *= 1 - np.asarray(Image.fromarray(dark.astype("uint8") * 255).filter(ImageFilter.GaussianBlur(1.5))).astype(float) / 255
        zone = window_zone(photo, cut)
        new = body * (1 - zone * (1 - both))

    out = (mask * 255).astype("uint8")
    out[..., 0] = (new * 255).astype("uint8")
    work = src / "cut_work"
    work.mkdir(exist_ok=True)
    Image.fromarray(out).save(work / "hero_mask_sam.png")
    p = np.asarray(photo).astype(float)
    for name, m in (("pred", body), ("po", new), ("sam", union.astype(float))):
        ov = p * (1 - 0.7 * m[..., None]) + np.array([255, 0, 255]) * 0.7 * m[..., None]
        if name != "pred":
            for pts in cells:
                for x, y in pts:
                    ov[max(0, y - 6):y + 6, max(0, x - 6):x + 6] = (0, 255, 0)
            for x, y in neg:
                ov[max(0, y - 5):y + 5, max(0, x - 5):x + 5] = (255, 255, 0)
        Image.fromarray(ov.clip(0, 255).astype("uint8")).save(work / f"maska_sam_{name}.png")
    print(f"body mask pixels {int((body > .5).sum())} -> {int((new > .5).sum())} (SAM union {int(union.sum())}); "
          f"{len(cells)} cells, {len(neg)} negative points; wrote {work}/hero_mask_sam.png")


if __name__ == "__main__":
    main()
