"""Cut a car out of its hero photo with a neural matting model (optional tool, needs `pip install "rembg[cpu]"`).

Writes a grey mask (white = car, grey = partly transparent; window glass cleared) to `cars/<car>/sources/cut_work/maska_rembg.png`
and a preview of it on the tile colours. Check the preview; to use the mask copy it to
`cars/<car>/sources/hero_cut.png` (build_index.py then uses it as drawn instead of its own automatic cut).

Usage:
    python cut_car.py --car doppler [--model isnet-general-use]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from PIL import Image, ImageFilter
import config


def clear_glass(photo, mask, veil=0.0):
    """The model keeps window glass as car (it is white like the studio): make the pale patches in the upper
    half of the car transparent again, so the tile colour shows through the windows. `veil` (0..1) keeps some
    of the glare: glass pixels get opacity veil + (1 - veil) * darkness, so white glass stays a pale veil and
    dark interior stays solid."""
    a = np.asarray(photo).astype(int)
    h = a.shape[0]
    mn, rng = a.min(2), a.max(2) - a.min(2)
    rows = np.arange(h)[:, None]
    car = np.asarray(mask) > 127
    ys = np.where(car.any(1))[0]
    upper = rows < ys[0] + 0.52 * (ys[-1] - ys[0])

    def mx(m, n=3):
        return np.asarray(Image.fromarray(m.astype("uint8") * 255).filter(ImageFilter.MaxFilter(n))) > 127

    def mn_(m, n):
        return np.asarray(Image.fromarray(m.astype("uint8") * 255).filter(ImageFilter.MinFilter(n))) > 127

    glass = mx(mn_((mn >= 200) & (rng < 14) & car & upper, 15), 15)               # core of the panes, specks dropped
    grow = car & upper & (mn >= 195) & (rng < 18)                                    # pale reflections at their edges
    for _ in range(9):
        glass = (mx(glass) & grow) | glass
    soft = Image.fromarray(glass.astype("uint8") * 255).filter(ImageFilter.GaussianBlur(2.5)).filter(ImageFilter.GaussianBlur(1.0))
    g = np.asarray(soft).astype(float) / 255
    glass_alpha = veil + (1 - veil) * np.clip((247 - mn) / 90.0, 0, 1)
    keep = 1 - g * (1 - glass_alpha)
    return Image.fromarray((np.asarray(mask).astype(float) * keep).astype("uint8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    ap.add_argument("--model", default="isnet-general-use")
    ap.add_argument("--glass-veil", type=float, default=0.0, help="0 = clear glass, 0.3 = pale veil of the glare")
    args = ap.parse_args()
    from rembg import new_session, remove

    src = config.car_sources(args.car)
    photo = Image.open(src / "hero.jpg").convert("RGB")
    out = remove(photo, session=new_session(args.model), only_mask=True, post_process_mask=True)
    out = clear_glass(photo, out, args.glass_veil)
    work = src / "cut_work"
    work.mkdir(exist_ok=True)
    out.save(work / "maska_rembg.png")
    a = np.asarray(out).astype(float)[..., None] / 255
    for name, tile in (("zluta", (245, 232, 189)), ("bila", (251, 251, 249))):
        comp = np.asarray(photo).astype(float) * a + np.array(tile, float) * (1 - a)
        Image.fromarray(comp.astype("uint8")).save(work / f"nahled_rembg_{name}.png")
    print(f"wrote {work}/maska_rembg.png (+ nahled_rembg_*.png)")


if __name__ == "__main__":
    main()
