"""Colour helpers shared by the pipeline.

  _load(path)                 image as an RGB array, transparent PNGs composited over white
  filament_rgb(path, ...)     measured colour of a filament product photo (see CLAUDE.md)
  neutral_class(name)         black / dark / white / grey from a colour name, else None
  lift_white(rgb, name, rules)  pull a measured white towards true white (see CLAUDE.md, "White lift")
  kraft_share(path)           share of a photo that looks like kraft cardboard (review flag)
  kraft_like_name / _rgb      cardboard-coloured name or RGB
  rgb_to_hex, hex_to_rgb, rgb_to_lab, delta_e_2000, delta_e_2000_many (Lab arrays)
  fold(s)                     lowercase ASCII without diacritics
"""
from __future__ import annotations
import math, re, unicodedata, warnings, numpy as np
from PIL import Image
# colour-science warns on import that optional SciPy/Matplotlib are missing; we use neither.
warnings.filterwarnings("ignore", message=r'"(SciPy|Matplotlib)" related API features are not available')
import colour

def _load(path):
    """Load an image as RGB, compositing transparent PNGs over white.

    PIL's `.convert("RGB")` on a palette PNG with a transparency entry returns the
    first palette colour (often green or black), not the rendered pixel.
    """
    im = Image.open(path)
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if has_alpha:
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    return np.asarray(im, dtype=np.uint8)

def _hsv(rgb):
    """(N, 3) RGB in 0-1 → hue in degrees, saturation, value, chroma (max-min), each (N,)."""
    maxc = rgb.max(axis=1); minc = rgb.min(axis=1)
    v = maxc
    s = np.where(maxc > 1e-6, (maxc - minc) / np.maximum(maxc, 1e-6), 0)
    dc = maxc - minc
    r, g, b = rgb[:,0], rgb[:,1], rgb[:,2]
    rc = np.where(dc > 0, (maxc - r) / np.maximum(dc, 1e-6), 0)
    gc = np.where(dc > 0, (maxc - g) / np.maximum(dc, 1e-6), 0)
    bc = np.where(dc > 0, (maxc - b) / np.maximum(dc, 1e-6), 0)
    h = np.zeros_like(maxc)
    h = np.where(maxc == r, bc - gc, h)
    h = np.where(maxc == g, 2 + rc - bc, h)
    h = np.where(maxc == b, 4 + gc - rc, h)
    return ((h / 6.0) % 1.0) * 360.0, s, v, dc

def fold(s):
    """Lowercase ASCII without diacritics: 'Černá' → 'cerna' (same as shoplib._fold)."""
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()

def kraft_share(path, *, drop_white_v=0.93, drop_white_s=0.08):
    """Share of non-background pixels that look like light kraft cardboard
    (hue 18-45°, saturation 0.18-0.6, value >= 0.35): refill boxes and spool cores.

    Good filament photos score ~0-0.05, a spool next to its box 0.5+. Beige or
    brown filament scores high too, so use this to *flag* a photo, never to
    mask pixels out of the measurement.
    """
    h, s, v, _dc = _hsv(_load(path).astype(np.float32).reshape(-1, 3) / 255.0)
    fg = ~((v > drop_white_v) & (s < drop_white_s))
    kraft = fg & (h >= 18) & (h <= 45) & (s >= 0.18) & (s < 0.6) & (v >= 0.35)
    return float(kraft.sum() / max(int(fg.sum()), 1))

_NEUTRAL_WORDS = {   # matched on the diacritics-folded colour name, first class wins
    "black": r"\b(cern|black|onyx|stealth|ebony|jet)\w*",
    "dark":  r"\b(antracit|anthracit|graphit|grafit|tmav\w*\s+sed|dark\s+gr[ae]y|charcoal|uhlov)\w*",
    "white": r"\b(bil[aeyi]|white|snow|snehobil|polar)\w*",
    "grey":  r"\b(sed[aeyi]|grey|gray|silver|stribrn|hlinik|alumin|concrete|cement)\w*",
}

# Colour names that legitimately sit in the kraft-cardboard band (diacritics-folded, lowercase).
_KRAFT_LIKE_NAMES = (r"bez|beige|sand|pisk|tan\b|taupe|khaki|linen|cream|krem|smetan|ivory|slonov|hned|brown|"
                     r"karamel|caramel|coffee|kav|telov|body|nude|skin|wood|drev|bronz|copper|med\b|medov|"
                     r"terra|cihl|clay|toffee|biscuit|almond|mandl|honey|desert|dune|poust|camel|mocha|balsa|"
                     r"latte|cappuccino|cork|kork|oak|dub|gold|zlat|mustard|horcic|ochre|okr|peach|broskv|"
                     r"apricot|merunk|salmon|losos|rose|pink|ruz|blush")

def kraft_like_name(name):
    """True when the colour name is a beige/brown/tan family colour (looks like cardboard)."""
    return re.search(_KRAFT_LIKE_NAMES, fold(name)) is not None

def kraft_like_rgb(rgb):
    """True when an (0-255) RGB colour sits in the kraft-cardboard band of kraft_share()."""
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return 18 <= h * 360 <= 45 and 0.18 <= s < 0.6 and v >= 0.35

def neutral_class(name):
    """'black' / 'white' / 'grey' when the colour name says so, else None."""
    n = fold(name)
    for cls, rx in _NEUTRAL_WORDS.items():
        if re.search(rx, n):
            return cls
    return None

def filament_rgb(path, *,
                  name=None,
                  min_chroma=0.0,
                  drop_hue_band=None,
                  exclude_kraft=False,
                  drop_white_v=0.93, drop_white_s=0.08,
                  drop_dark_v=0.15,
                  drop_yellow_watermark=True,
                  min_valid_pixels=200,
                  verbose=False,
                  trace=None):
    """Measured colour of a filament product photo → ((r, g, b) | None, pixel count).

    Steps (thresholds and their reasons: CLAUDE.md, "filament_rgb() branches…"):
      1. Drop studio-white background (v > 0.93, s < 0.08) and shadows (v < 0.15).
      2. Drop dark cardboard (hue 15-45°, s 0.15-0.55, v < 0.65), the yellow Smart3D
         watermark (hue 42-62°, s > 0.40, only while it is < 4 % of the foreground)
         and a per-brand `drop_hue_band`.
      3. Coloured when the colourful pixels (s >= 0.10, chroma >= `min_chroma`) are
         > max(200, 2 %) of what is left and their mean saturation > 0.15: median of
         the pixels within ±15° of the saturation²-weighted dominant hue.
      4. Otherwise neutral: median of the rest, minus light kraft and dark spool
         flanges when enough remains without them.
      5. Kraft second pass when the result looks like cardboard but the name doesn't.
    Returns (None, 0) when no pixel survives step 1.

    `trace`: pass a dict to get `trace["mask"]`, an (H, W) bool array of the pixels the
    final median was taken from (review_sheet.py draws it). Costs nothing otherwise.

    `name` (colour name) helps neutral filaments: when it says black / white /
    grey, the median is taken from dark / light / mid-grey low-saturation pixels
    only, with kraft cardboard (refill boxes, spool cores) excluded — otherwise
    black and white windings get dropped as shadow / background and the median
    lands on the box or the spool.
    """
    arr = _load(path).astype(np.float32) / 255.0
    H, W, _ = arr.shape
    rgb = arr.reshape(-1, 3)
    h_deg, s, v, dc = _hsv(rgb)

    # Studio background (very light, unsaturated)
    is_bg_white = (v > drop_white_v) & (s < drop_white_s)
    # Shadows
    is_shadow = v < drop_dark_v
    # Brown box / spool cardboard: darker than beige pigment (beige filament is
    # usually v > 0.65, cardboard around 0.35-0.60)
    is_cardboard = (h_deg >= 15) & (h_deg <= 45) & (s >= 0.15) & (s < 0.55) & (v < 0.65)
    # Smart3D yellow watermark (high saturation, a specific hue)
    is_watermark = (h_deg >= 42) & (h_deg <= 62) & (s > 0.40) if drop_yellow_watermark else np.zeros_like(v, dtype=bool)
    # The watermark is thin text: when "watermark yellow" covers a real area, it's a yellow filament.
    fg = ~(is_bg_white | is_shadow)
    if is_watermark.sum() > 0.04 * max(int(fg.sum()), 1):
        is_watermark = np.zeros_like(v, dtype=bool)
    # Light kraft cardboard (refill boxes, spool cores) — same band as kraft_share()
    is_kraft = (h_deg >= 18) & (h_deg <= 45) & (s >= 0.18) & (s < 0.6) & (v >= 0.35)

    # `drop_hue_band` (per-brand hint): [hue_lo, hue_hi, sat_lo, sat_hi] of a coloured spool
    # or stand that is in every photo of the brand (SUNLU: blue-grey spool), any brightness.
    if drop_hue_band:
        h_lo, h_hi, s_lo, s_hi = drop_hue_band
        is_prop = (h_deg >= h_lo) & (h_deg <= h_hi) & (s >= s_lo) & (s <= s_hi)
    else:
        is_prop = np.zeros_like(v, dtype=bool)

    cls = neutral_class(name) if name else None
    if cls:
        base = ~(is_bg_white | is_kraft | is_watermark | is_prop) & (s < 0.25)
        if cls == "black":
            pick = base & (v < 0.40)                       # keep the "shadow" pixels: that's the filament
        elif cls == "dark":
            pick = base & (v < 0.50)                       # anthracite / graphite: dark, not quite black
        elif cls == "white":
            pick = base & (v >= 0.70) & (s < 0.12)
            # The lit half: shading between windings would otherwise grey the white down.
            if int(pick.sum()) >= 2 * min_valid_pixels:
                pick &= v >= np.median(v[pick])
        else:
            pick = base & (v >= drop_dark_v)
            dark = pick & (v < 0.30)                       # black spool flanges next to a grey winding
            if dark.sum() < 0.6 * max(int(pick.sum()), 1):
                pick &= ~dark
            paper = pick & (v >= 0.86) & (s < 0.08)        # white spool labels / stickers
            if (pick & ~paper).sum() >= 0.25 * max(int(pick.sum()), 1):
                pick &= ~paper
        if int(pick.sum()) >= min_valid_pixels:
            med = np.median(rgb[pick], axis=0)
            if verbose: print(f"neutral[{cls}]: picked={int(pick.sum())}")
            if trace is not None: trace["mask"] = pick.reshape(H, W)
            return tuple((med * 255).round().astype(int).tolist()), int(pick.sum())

    # exclude_kraft (second pass, see the end): drop the whole cardboard-brown hue band,
    # shaded cardboard included — the name already says the filament isn't brown.
    is_brown = (h_deg >= 12) & (h_deg <= 48) & (s >= 0.15) & (v >= 0.12) if exclude_kraft else False
    valid = ~(is_bg_white | is_shadow | is_cardboard | is_watermark | is_brown | is_prop)
    valid_count = int(valid.sum())

    if valid_count < min_valid_pixels:
        # Too few pixels survived the filters: retry with only background and shadows dropped
        valid = ~(is_bg_white | is_shadow)
        valid_count = int(valid.sum())
        if valid_count == 0:
            return None, 0          # nothing measurable; (0,0,0) would match black paints

    valid_rgb = rgb[valid]
    valid_s = s[valid]
    valid_h = h_deg[valid]
    mean_sat = float(valid_s.mean())

    # Keep grey pixels (s < 0.10) out of the hue histogram: their "hue" is numerical noise
    # and, when there are enough of them, would dominate the result.
    # `min_chroma` (per-brand hint, see shops/_defaults.yaml measure_hints): also require
    # absolute chroma (max-min). HSV inflates the saturation of dark pixels, so Aurapol's
    # slightly bluish black spool outvotes a pastel winding. Not global: a dark bronze or
    # olive-brown filament has the same tiny chroma as that spool.
    colorful_mask = (valid_s >= 0.10) & (dc[valid] >= min_chroma)
    colorful_h = valid_h[colorful_mask]
    colorful_s = valid_s[colorful_mask]
    colorful_rgb = valid_rgb[colorful_mask]
    colorful_mean_sat = float(colorful_s.mean()) if len(colorful_s) > 0 else 0.0

    # Relative, not just > 200: on a large photo a few hundred anti-aliased edge pixels of a
    # removed spool would otherwise turn a pale neutral winding into a "coloured" filament.
    if len(colorful_h) > max(200, 0.02 * len(valid_rgb)) and colorful_mean_sat > 0.15:
        # Coloured filament: dominant hue of the colourful pixels
        hist, _ = np.histogram(colorful_h, bins=360, range=(0,360), weights=colorful_s**2)
        pad = np.r_[hist[-11:], hist, hist[:11]]
        sm = np.convolve(pad, np.ones(11)/11, mode='valid')[5:5+360]
        peak = int(np.argmax(sm))
        dist = np.minimum(np.abs(colorful_h - peak), 360 - np.abs(colorful_h - peak))
        sel = dist <= 15
        # Within the hue window keep the saturated pixels: a box or spool core of the
        # same hue (orange filament next to kraft) is far less saturated than the filament.
        # Only for strongly saturated filaments (p90 >= 0.75) photographed with a kraft box
        # or core (> 12 % of the foreground): elsewhere the least saturated pixels are the
        # lit highlights, and dropping them would darken the colour.
        p90 = float(np.percentile(colorful_s[sel], 90)) if sel.sum() else 0.0
        kraft_photo = is_kraft.sum() > 0.12 * max(int(fg.sum()), 1)
        if sel.sum() >= 50 and p90 >= 0.75 and kraft_photo:
            strong = sel & (colorful_s >= 0.6 * p90)
            if strong.sum() >= 50:
                sel = strong
        if sel.sum() < 50:
            med = np.median(colorful_rgb, axis=0)
            used = colorful_mask
        else:
            med = np.median(colorful_rgb[sel], axis=0)
            used = np.zeros(len(valid_rgb), dtype=bool)
            used[np.flatnonzero(colorful_mask)[sel]] = True
        if verbose: print(f"colored: peak={peak}°, mean_sat={colorful_mean_sat:.2f}, in-window={int(sel.sum())}, colorful={len(colorful_h)}")
    else:
        # Neutral filament (white/beige/grey/pastel): median of everything that passed; leave out
        # kraft cardboard (box, spool core) when enough remains without it (a beige filament won't).
        keep = np.ones(len(valid_rgb), dtype=bool)
        not_kraft = ~is_kraft[valid]
        if not_kraft.sum() >= max(min_valid_pixels, 0.6 * len(valid_rgb)):
            keep &= not_kraft
        # Dark achromatic pixels are usually the spool flanges (Aurapol: black spool + grey
        # stand next to a pastel or white winding); drop them when enough remains without.
        valid_v = v[valid]
        spool = (valid_v < 0.35) & (valid_s < 0.25)
        if (keep & ~spool).sum() >= max(min_valid_pixels, 0.3 * keep.sum()):
            keep &= ~spool
            # A pastel winding next to a grey stand: prefer the tinted pixels.
            tinted = keep & (valid_s >= 0.08) & (valid_v >= 0.5)
            if tinted.sum() >= max(min_valid_pixels, 0.3 * keep.sum()):
                keep = tinted
        med = np.median(valid_rgb[keep], axis=0)
        used = keep
        if verbose: print(f"neutral: mean_sat={mean_sat:.2f}, colorful_mean={colorful_mean_sat:.2f}, valid={valid_count}, colorful={len(colorful_h)}")

    out = (med * 255).round().astype(int).tolist()
    if trace is not None:
        full = np.zeros(H * W, dtype=bool)
        full[np.flatnonzero(valid)[used]] = True
        trace["mask"] = full.reshape(H, W)
    # Cardboard won: the photo is mostly kraft (refill box, LUME's cardboard spool, Aurapol's
    # beige stand), the result is kraft-coloured, and the name says it isn't a beige/brown
    # filament. Measure again without kraft pixels.
    if (name and not exclude_kraft and kraft_like_rgb(out) and not kraft_like_name(name)
            and is_kraft.sum() > 0.12 * max(int(fg.sum()), 1)):
        again_trace = {} if trace is not None else None
        again, n = filament_rgb(path, name=name, min_chroma=min_chroma, drop_hue_band=drop_hue_band,
                                exclude_kraft=True,
                                drop_white_v=drop_white_v, drop_white_s=drop_white_s, drop_dark_v=drop_dark_v,
                                drop_yellow_watermark=drop_yellow_watermark, min_valid_pixels=min_valid_pixels,
                                verbose=verbose, trace=again_trace)
        # Only when a real non-cardboard object is left (>= 5 % of the foreground) and it isn't
        # just the black spool: a tan filament with an unknown name ("Mukha") has nothing else.
        spool_like = again is not None and max(again) < 0.30 * 255 and max(again) - min(again) < 0.035 * 255
        if again is not None and n >= max(min_valid_pixels, 0.05 * int(fg.sum())) and not (
                spool_like and neutral_class(name) not in ("black", "dark")):
            if verbose: print(f"kraft won ({rgb_to_hex(out)}), re-measured without kraft → {rgb_to_hex(again)}")
            if trace is not None: trace["mask"] = again_trace["mask"]
            return again, n
    return tuple(out), valid_count

def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)

def hex_to_rgb(hx):
    """'#AABBCC' or 'AABBCC' → [170, 187, 204]; None when it isn't a 6-digit hex."""
    h = str(hx or "").lstrip("#")
    try:
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)] if len(h) == 6 else None
    except ValueError:
        return None

def rgb_to_lab(rgb):
    a = np.asarray(rgb, dtype=float) / 255.0
    xyz = colour.sRGB_to_XYZ(a)
    return colour.XYZ_to_Lab(xyz)

def lab_to_rgb(lab):
    a = colour.XYZ_to_sRGB(colour.Lab_to_XYZ(np.asarray(lab, dtype=float)))
    return [int(round(float(c))) for c in np.clip(a, 0, 1) * 255]

def lift_white(rgb, name, rules):
    """Measured white → lighter, less grey. Photos cannot measure white above ~#EC (the studio
    background cut-off in filament_rgb()) and shade the windings, so a filament named white
    measures grey. `rules` = `white_lift` of shops/_defaults.yaml: ordered [{match, L, pull,
    chroma}], first rule whose regex hits the folded colour name wins. Lightness moves `pull`
    (default 1) of the way to `L`, never down; a*/b* are scaled by `chroma` (default 1).
    Colours that are not named white, or that no rule matches, come back unchanged."""
    if neutral_class(name) != "white":
        return list(rgb)
    n = fold(name)
    for rule in rules or []:
        if re.search(rule["match"], n):
            break
    else:
        return list(rgb)
    L, a, b = rgb_to_lab(rgb)
    target, pull = float(rule.get("L", 100)), float(rule.get("pull", 1))
    k = float(rule.get("chroma", 1))
    if pull <= 0 or L >= target - 0.5:            # already there (also keeps a second pass from drifting)
        return list(rgb)
    out = lab_to_rgb([L + pull * (target - L), a * k, b * k])
    return out if sum(out) > sum(rgb) else list(rgb)

def delta_e_2000(rgb_a, rgb_b):
    la = rgb_to_lab(rgb_a)
    lb = rgb_to_lab(rgb_b)
    return float(colour.delta_E(la, lb, method="CIE 2000"))

def delta_e_2000_many(lab_a, lab_b):
    """ΔE2000 between Lab colours, broadcast: one (3,) target against an (N, 3) pool → (N,).
    Same numbers as delta_e_2000(), without converting and calling once per pair."""
    lab_a, lab_b = np.broadcast_arrays(np.asarray(lab_a, dtype=float), np.asarray(lab_b, dtype=float))
    return np.asarray(colour.delta_E(lab_a, lab_b, method="CIE 2000"), dtype=float)
