"""Build the site's root page: one big tile per published car, the car recolours through its best filaments.

Reads every `cars/*/car.json` with "publish": true, its `data/matches.json` and `data/hero.json`,
and writes `site/index.html` (self-contained, committed; scripts/build_site.sh copies it into _site/).

Per car, optional `"index": {"color": "#RRGGBB"}` in car.json is the tile's primary colour (the one
shown at rest); without it the best-matching filament is used. A tile's look comes from
`themes/<theme>/tile.css` (scoped `.tile--<theme>`) and `tile.html` (decoration that may overflow the
frame); a theme without them gets the neutral default tile.

Usage:
    python build_index.py
"""
import base64, html, io, json, re, sys
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import config
from build_html import counter_html
from color_tools import delta_e_2000, hex_to_rgb, rgb_to_lab
from compute_matches import NEON_PENALTY, NEON_PAINT_CHROMA

SITE_DIR = config.ROOT / "site"
THEMES_DIR = config.ROOT / "themes"
REPO_URL = "https://github.com/martincollar/car-paint-filaments"
AUTHOR = "Martin Kolář"
PALETTE_SIZE = 8        # colours a tile cycles through, primary included
MIN_SPACING = 12.0      # ΔE2000 two colours of one tile must differ by, so no near-repeats
MAX_MATCH_DE = 8.0      # a colour only counts as a "best" candidate below this ΔE to some paint


def penalised(cand, colour):
    """a neon filament for a paint that is not neon itself (same rule as compute_matches.py: such a filament only
    looks right on a car when the paint is neon, and plain ΔE flatters it)"""
    if not cand.get("neon"):
        return False
    lab = rgb_to_lab(colour["rgb"])
    return float(np.hypot(lab[1], lab[2])) < NEON_PAINT_CHROMA


def rank(cand, colour):
    return cand["delta_e"] + (NEON_PENALTY if penalised(cand, colour) else 0.0)


def best_per_hex(matches):
    """{hex: candidate} over every region, PLA and PETG; per hex the candidate closest to a paint."""
    best = {}
    for colours in matches.values():
        for colour in colours:
            for cand in colour.get("pla", []) + colour.get("petg", []) + colour.get("asa", []):
                hx = (cand.get("hex") or "").upper()
                if hex_to_rgb(hx) and not penalised(cand, colour) and (hx not in best or cand["delta_e"] < best[hx]["delta_e"]):
                    best[hx] = cand
    return best


def pick_palette(matches, primary=None, size=PALETTE_SIZE, spacing=MIN_SPACING, max_de=MAX_MATCH_DE):
    """[{hex, label}] for one tile, primary first, best candidates after, none within `spacing` of another."""
    best = best_per_hex(matches)
    ranked = sorted((c for c in best.values() if c["delta_e"] <= max_de), key=lambda c: c["delta_e"])
    out = []

    def label(hx):
        c = best.get(hx)
        return f'{c["brand"]} {c["color_name"]}' if c else ""

    def far_enough(hx):
        return all(delta_e_2000(hex_to_rgb(hx), hex_to_rgb(o["hex"])) >= spacing for o in out)

    primary = (primary or "").upper() or None
    if primary and hex_to_rgb(primary):
        out.append({"hex": primary, "label": label(primary)})
    for cand in ranked:
        if len(out) >= size:
            break
        hx = cand["hex"].upper()
        if far_enough(hx) if out else True:
            out.append({"hex": hx, "label": label(hx)})
    return out


def named_palette(matches, paints):
    """[{hex, label, paint, year}] in the order of `paints`: for every paint name its best PLA filament.
    A name may carry a year ("Lemon Twist 1973") to pick one chip when the same name was used in several years;
    without a year the chip whose PLA match is closest wins."""
    out = []
    for entry in paints:
        m = re.match(r"^(.*?)(?:\s+(\d{4}))?$", entry.strip())
        name, year = m.group(1).lower(), m.group(2)
        best = None
        for colours in matches.values():
            for colour in colours:
                if colour["name"].lower() != name or (year and str(colour.get("year")) != year):
                    continue
                for cand in colour.get("pla", []):
                    if best is None or rank(cand, colour) < rank(best[0], best[1]):
                        best = (cand, colour)
        if best is None:
            known = sorted({c["name"] for cs in matches.values() for c in cs})
            raise ValueError(f"paint {entry!r} has no PLA match in the car's data (names: {', '.join(known)})")
        cand, colour = best
        out.append({"hex": cand["hex"].upper(), "label": f'{cand["brand"]} {cand["color_name"]}',
                    "paint": colour["name"], "year": colour.get("year")})
    return out


def year_span(years):
    if not years:
        return ""
    lo, hi = min(years), max(years)
    if lo == hi:
        return str(lo)
    return f"{lo}–{str(hi)[-2:]}" if lo // 100 == hi // 100 else f"{lo}–{hi}"


def theme_file(theme, name):
    p = THEMES_DIR / theme / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _smooth(mask, radius):
    """binary mask with its staircase edges rounded off (blur, then threshold)"""
    im = Image.fromarray(mask.astype("uint8") * 255).filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(im) > 127


def _bleed(rgb, core, steps=10):
    """RGB where every pixel outside `core` takes the colour of its nearest core pixels (up to `steps` px away), so
    a soft alpha edge never shows the studio white that anti-aliasing mixed into the border pixels."""
    out, valid = rgb.astype(float), core.copy()
    for _ in range(steps):
        todo = ~valid
        if not todo.any():
            break
        acc, cnt = np.zeros_like(out), np.zeros(valid.shape)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    v = np.roll(np.roll(valid, dy, 0), dx, 1)
                    acc += np.roll(np.roll(out, dy, 0), dx, 1) * v[..., None]
                    cnt += v
        sel = todo & (cnt > 0)
        out[sel] = acc[sel] / cnt[sel][:, None]
        valid |= sel
    return out


def _png(arr):
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def silhouette(photo_uri, manual=None):
    """(cut, fg) data URIs for one studio photo.
    cut: grey PNG, 255 = car. The near-white background, glass and the photographed floor shadow are not car (the
    page draws the shadow back as a multiply layer, so it stays soft and takes the tile's colour).
    fg: the photo with every pixel outside the (eroded) car taking its nearest car colour, so alpha edges carry no
    white fringe. `manual` is an optional hand-made grey mask (same picture, white = car, black = clear, greys = partly
    transparent) that replaces the automatic one and is used as drawn."""
    raw = Image.open(io.BytesIO(base64.b64decode(photo_uri.split(",", 1)[1]))).convert("RGB")
    a = np.asarray(raw).astype(int)
    h, w = a.shape[:2]
    mn, rng = a.min(2), a.max(2) - a.min(2)
    rows = np.arange(h)[:, None]
    soft = None
    if manual is not None:
        soft = np.asarray(manual.convert("L").resize((w, h), Image.LANCZOS))      # grey = opacity, used as drawn
        car = soft > 127
    else:
        studio = (mn >= 236) & (rng < 14)
        floor = (mn >= 85) & (rng < 14) & (rows >= int(h * 0.70))          # soft floor shadow, below the sills only
        pale = (mn >= 190) & (rng < 14) & (rows >= int(h * 0.60))          # its pale edge, just under the body
        light = studio | floor | pale

        def background(mask):
            """pixels of `mask` (bool array) connected to the image border"""
            im = Image.fromarray(mask.astype("uint8") * 255).copy()
            seeds = [(x, y) for x in range(0, w, 8) for y in (0, h - 1)] + [(x, y) for y in range(0, h, 8) for x in (0, w - 1)]
            for p in seeds:
                if im.getpixel(p) == 255:
                    ImageDraw.floodfill(im, p, 128)
            return np.asarray(im.copy()) == 128

        car = ~background(light)
        half = Image.fromarray(car.astype("uint8") * 255).resize((w // 2, h // 2), Image.BILINEAR)   # close gaps (open windscreen)
        half = half.filter(ImageFilter.MaxFilter(21)).filter(ImageFilter.MinFilter(21))
        car = np.asarray(half.resize((w, h), Image.BILINEAR)) > 127
        car |= ~background(~car)                                             # holes inside the silhouette are car
        # studio-white patches inside the car above its middle are glass: let the tile show through them (the
        # white sidewalls sit below the middle and stay opaque)
        ys = np.where(car.any(1))[0]
        glass = studio & car & (rows < ys[0] + 0.52 * (ys[-1] - ys[0]))
        glass = np.asarray(Image.fromarray(glass.astype("uint8") * 255).filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MaxFilter(7))) > 127
        grow = car & (mn >= 205) & (rng < 18) & (rows < ys[0] + 0.52 * (ys[-1] - ys[0]))   # pale reflections at the glass edge
        for _ in range(5):
            glass = (np.asarray(Image.fromarray(glass.astype("uint8") * 255).filter(ImageFilter.MaxFilter(3))) > 127) & grow | glass
        car = _smooth(car & ~_smooth(glass, 2.0), 1.6)
    if soft is None:
        core = np.asarray(Image.fromarray(car.astype("uint8") * 255).filter(ImageFilter.MinFilter(5))) > 127
        alpha = np.asarray(Image.fromarray(car.astype("uint8") * 255).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.0)))
    else:       # only fully opaque pixels away from any edge supply colour to the bleed
        core = np.asarray(Image.fromarray((soft >= 245).astype("uint8") * 255).filter(ImageFilter.MinFilter(5))) > 127
        alpha = soft
    fg = _bleed(a, core).clip(0, 255).astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(fg).save(buf, "JPEG", quality=88)
    return _png(alpha), "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def collect_car(car):
    meta = config.car_meta(car)
    data = config.car_data(car)
    matches = json.loads((data / "matches.json").read_text(encoding="utf-8"))
    hero = json.loads((data / "hero.json").read_text(encoding="utf-8"))
    manual_path = config.car_sources(car) / "hero_cut.png"     # optional hand-made mask, white = car
    cut, fg = silhouette(hero["photo"], Image.open(manual_path) if manual_path.exists() else None)
    primary = (meta.get("index") or {}).get("color")
    theme = meta.get("theme") or "doppler"
    return {
        "slug": car,
        "display": meta.get("display") or meta.get("name") or car,
        "tagline": meta.get("script_tagline") or "",
        "years": year_span(meta.get("years") or []),
        "colours": len(next(iter(matches.values()), [])),
        "theme": theme,
        "palette": (named_palette(matches, meta["index"]["paints"]) if (meta.get("index") or {}).get("paints")
                    else pick_palette(matches, primary)),
        "hero": hero,
        "cut": cut,
        "fg": fg,
        "order": meta.get("index", {}).get("order", 100),
        "buy_url": (meta.get("index") or {}).get("buy_url") or "",
    }


def fonts_href(themes):
    fams = []
    for t in themes:
        for fam in re.findall(r"family=[^&\s]+", theme_file(t, "fonts.txt") + " " + theme_file(t, "tile-fonts.txt")):
            if fam not in fams:
                fams.append(fam)
    return "https://fonts.googleapis.com/css2?" + "&".join(fams) + "&display=swap" if fams else ""


def split_name(text):
    """(html, length): one span per letter so a theme can bend the title (--i = index, --n = length on the heading);
    letters stay together per word, so a long title can only wrap between words."""
    words, idx = [], 0
    for w in text.split(" "):
        chars = "".join(f'<span class="ch" style="--i:{idx + k}" aria-hidden="true">{html.escape(ch)}</span>' for k, ch in enumerate(w))
        words.append(f'<span class="w">{chars}</span>')
        idx += len(w) + 1
    return " ".join(words), len(text)


def offsets_css(themes):
    """element offsets saved by the layout editor (`?edit` on scripts/serve_preview.py), applied after the theme CSS"""
    out = ""
    for t in themes:
        out += theme_file(t, "tile-offsets.css") + theme_file(t, "tile-colors.css")
        mobile = theme_file(t, "tile-offsets-mobile.css")
        if mobile.strip():
            out += f"@media (max-width: 520px) {{\n{mobile}}}\n"
    return out


def tile_html(c):
    esc = html.escape
    first = c["palette"][0]
    meta = " · ".join(x for x in (c["years"], f'{c["colours"]} paint colours') if x)
    name_html, name_len = split_name(c["display"])
    tagline = f'<p class="tile-tag">{esc(c["tagline"])}</p>' if c["tagline"] else ""
    buy = (f'\n    <a class="tile-buy" href="{esc(c["buy_url"])}" target="_blank" rel="noopener">Buy files</a>'
           if c["buy_url"] else "")
    return f"""
<article class="tile tile--{esc(c['theme'])}" data-car="{esc(c['slug'])}" style="--tile-colour:{first['hex']}">
  <div class="tile-frame"></div>
  <div class="tile-deco" aria-hidden="true">{theme_file(c['theme'], 'tile.html')}</div>
  <div class="tile-stage" aria-hidden="true">
    <canvas class="tile-shade"></canvas>
    <img class="tile-photo" alt="" src="{c['hero']['photo']}">
    <canvas class="tile-canvas"></canvas>
  </div>
  <div class="tile-text">
    <h2 class="tile-name" style="--n:{name_len}"><a href="{esc(c['slug'])}/" aria-label="{esc(c['display'])}">{name_html}</a></h2>
    {tagline}
    <p class="tile-meta">{esc(meta)}</p>
  </div>
  <div class="tile-foot">
    <span class="tile-label">{esc(first['label'])}</span>
    <a class="tile-open" href="{esc(c['slug'])}/">Pick a filament &rarr;</a>{buy}
  </div>
</article>"""


# Retro wordmark (styles in PAGE_CSS); flip to True to replace the plain heading on the root page.
SHOW_WORDMARK = False
WORDMARK_HTML = ('<h1 class="wordmark" aria-label="Car paint filaments"><span class="wm-script" aria-hidden="true">Car paint</span>'
                 '<span class="wm-slab" aria-hidden="true">Filaments</span></h1>')

PAGE_CSS = """
:root { --page: #ecebe7; --tile: #fbfbf9; --ink: #1d1d1b; --muted: #6b6a66; --line: #d9d7d0; --accent: #1d1d1b; }
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--page); color: var(--ink); overflow-x: clip;
       font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
a { color: inherit; }
.site-head, .site-foot { max-width: 1180px; margin: 0 auto; padding: 28px 28px; }
.site-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 6px 24px;
             padding-top: 36px; }
.site-head h1 { margin: 0; font-size: 1.15rem; font-weight: 700; letter-spacing: .01em; }
.wordmark { display: flex; flex-direction: column; align-items: flex-start; margin: 0; line-height: 1; }
.wm-script { font: 400 2.9rem/1 "Pacifico", cursive; color: var(--ink); transform: rotate(-4deg); transform-origin: left bottom;
             margin: 0 0 -.45rem .5rem; position: relative; z-index: 1;
             text-shadow: -2px -2px 0 var(--page), 2px -2px 0 var(--page), -2px 2px 0 var(--page), 2px 2px 0 var(--page), 3px 3px 0 var(--ink); }
.wm-slab { font: 400 3rem/1 "Alfa Slab One", Georgia, serif; text-transform: uppercase; letter-spacing: .07em; color: var(--ink);
           padding-bottom: .65rem; position: relative; }
.wm-slab::after { content: ""; position: absolute; left: 0; right: .07em; bottom: 0; height: 10px;
                  background: linear-gradient(var(--ink) 0 5px, transparent 5px 7px, var(--ink) 7px 9px); }
.site-head p { margin: 0; color: var(--muted); max-width: 46ch; }
main { max-width: 1180px; margin: 0 auto; padding: 24px 28px 56px; display: grid; gap: 64px 76px;
       grid-template-columns: repeat(auto-fill, minmax(min(100%, 440px), 1fr)); }
.site-foot { border-top: 1px solid var(--line); color: var(--muted); font-size: .85rem;
             display: flex; flex-wrap: wrap; gap: 6px 24px; justify-content: space-between; }

/* neutral default tile; a theme's tile.css restyles it through `.tile--<theme>` */
.tile { position: relative; width: 100%; max-width: 470px; justify-self: center; min-height: 340px; padding: 12px 24px 20px; display: flex; flex-direction: column;
        justify-content: space-between; --stage-w: 121%; --stage-left: -10.5%; --stage-bottom: 30px; }
.tile-frame { position: absolute; inset: 0; background: var(--tile); border: 2px solid var(--ink); border-radius: 14px;
              box-shadow: 0 10px 24px -14px rgba(0,0,0,.35); }
.tile-deco { position: absolute; inset: 0; pointer-events: none; }
.tile-stage { position: absolute; left: var(--stage-left); bottom: var(--stage-bottom); width: var(--stage-w);
              aspect-ratio: 1000 / 640; pointer-events: none; }
.tile-photo, .tile-shade, .tile-canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
.tile-photo, .tile-shade { mix-blend-mode: multiply; z-index: 1; }  /* floor shadow melts into the tile colour */
.tile-canvas { z-index: 4; }                                         /* the cut-out car: above frame, text and decoration */
.tile-photo { filter: brightness(1.032); }
.tile.ready .tile-photo { visibility: hidden; }
.js .tile:not(.ready) .tile-photo { opacity: 0; }   /* no flash of the photo's own colour before the recolour */
.tile-text { position: relative; z-index: 3; }
.tile-name { margin: 0; font-size: 1.7rem; line-height: 1.1; }
.tile-name a { text-decoration: none; }
.tile-name .w { white-space: nowrap; }
.tile-name .ch { display: inline-block; }
@media (hover: hover) and (pointer: fine) {   /* mouse: the whole tile is the link; touch: a tap cycles colours instead */
  .tile-name a::after { content: ""; position: absolute; inset: -22px -24px -300px; }
}
.tile-tag { margin: 6px 0 0; color: var(--muted); }
.tile-meta { margin: 4px 0 0; font-size: .85rem; color: var(--muted); }
.tile-foot { position: relative; z-index: 3; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: auto;
             padding-top: 202px; }
.tile-label { font-size: .7rem; color: var(--muted); opacity: .65; min-height: 1.3em; flex: 1 0 100%; min-width: 0; }
.tile-open { position: relative; z-index: 4; font-size: .9rem; font-weight: 600; text-decoration: none; padding: 7px 14px;
             border: 2px solid var(--ink); border-radius: 999px; background: var(--tile); white-space: nowrap; }
.tile-open:hover, .tile-open:focus-visible { background: var(--ink); color: var(--tile); }
.tile-buy { position: relative; z-index: 4; font-size: .9rem; font-weight: 600; text-decoration: none; padding: 7px 14px;
            border: 2px solid var(--ink); border-radius: 999px; background: transparent; white-space: nowrap; }
.tile-buy:hover, .tile-buy:focus-visible { background: var(--ink); color: var(--tile); }
.tile-name a:focus-visible { outline: 3px solid #2563eb; outline-offset: 6px; }
@media (max-width: 520px) {
  .site-head, .site-foot { padding-left: 26px; padding-right: 26px; }
  main { padding-left: 26px; padding-right: 26px; gap: 54px; }
  .tile { padding: 18px 18px 16px; --stage-w: 108%; --stage-left: -4%; }
  .tile-name { font-size: 1.45rem; }
  .tile-foot { padding-top: 175px; }
}
"""

PAGE_JS = """
(function () {
  var CARS = __CARS__;
  var editing = /[?&]edit\\b/.test(location.search);       // layout editor (scripts/serve_preview.py): tiles stay still
  if (editing) { var es = document.createElement('script'); es.src = '/__editor.js'; document.head.appendChild(es); }
  var M = [[0.4124564,0.3575761,0.1804375],[0.2126729,0.7151522,0.0721750],[0.0193339,0.1191920,0.9503041]];
  var Mi = [[3.2404542,-1.5371385,-0.4985314],[-0.9692660,1.8760108,0.0415560],[0.0556434,-0.2040259,1.0572252]];
  var WP = [0.95047, 1, 1.08883], BG = 247;   // the studio photos' background grey, levelled to white so multiply hides it
  function lin(c) { c /= 255; return c > 0.04045 ? Math.pow((c + 0.055) / 1.055, 2.4) : c / 12.92; }
  function gam(c) { c = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055; return Math.max(0, Math.min(1, c)) * 255; }
  function f(t) { return t > 216 / 24389 ? Math.cbrt(t) : (24389 / 27 * t + 16) / 116; }
  function finv(t) { var t3 = t * t * t; return t3 > 216 / 24389 ? t3 : (116 * t - 16) / (24389 / 27); }
  function toLab(r, g, b) {
    r = lin(r); g = lin(g); b = lin(b);
    var fx = f((M[0][0]*r + M[0][1]*g + M[0][2]*b) / WP[0]), fy = f(M[1][0]*r + M[1][1]*g + M[1][2]*b),
        fz = f((M[2][0]*r + M[2][1]*g + M[2][2]*b) / WP[2]);
    return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
  }
  function hexRgb(h) { return [1, 3, 5].map(function (i) { return parseInt(h.substr(i, 2), 16); }); }
  function img(src) { return new Promise(function (ok) { var i = new Image(); i.onload = function () { ok(i); }; i.src = src; }); }

  var fine = matchMedia('(hover: hover) and (pointer: fine)').matches,
      calm = matchMedia('(prefers-reduced-motion: reduce)').matches;

  function Tile(el, car) {
    var t = this; t.el = el; t.car = car; t.i = 0; t.cache = {}; t.timer = 0; t.anim = 0; t.cur = null;
    t.cv = el.querySelector('.tile-canvas'); t.sh = el.querySelector('.tile-shade'); 
    t.label = el.querySelector('.tile-label');
    t.photo = el.querySelector('.tile-photo');
    Promise.all([img(t.photo.src), img(car.hero.fg), img(car.hero.mask), img(car.hero.cut)]).then(function (a) { t.setup(a[0], a[1], a[2], a[3]); });
  }
  Tile.prototype.setup = function (photo, fg, mask, cut) {
    var t = this, W = t.W = photo.width, H = t.H = photo.height, c = document.createElement('canvas');
    c.width = W; c.height = H;
    var x = c.getContext('2d', { willReadFrequently: true });
    x.drawImage(photo, 0, 0); var shade = x.getImageData(0, 0, W, H), sp = shade.data;      // the original: only for the shadow
    x.clearRect(0, 0, W, H); x.drawImage(fg, 0, 0); var d = t.base = x.getImageData(0, 0, W, H);   // the car, edges bled outwards
    x.clearRect(0, 0, W, H); x.drawImage(mask, 0, 0); var mk = x.getImageData(0, 0, W, H).data, n = W * H, px = d.data;
    for (var j = 0; j < px.length; j += 4) for (var k = 0; k < 3; k++) {
      px[j + k] = Math.min(255, px[j + k] * 255 / BG); sp[j + k] = Math.min(255, sp[j + k] * 255 / BG);
    }
    x.clearRect(0, 0, W, H); x.drawImage(cut, 0, 0); var ct = x.getImageData(0, 0, W, H).data;
    for (j = 0; j < px.length; j += 4) {     // alpha = silhouette; the shadow layer is the photo with the car painted white
      var ca = ct[j] / 255; px[j + 3] = ct[j];
      for (k = 0; k < 3; k++) sp[j + k] = sp[j + k] * (1 - ca) + 255 * ca;
      sp[j + 3] = 255;
    }
    t.sh.width = W; t.sh.height = H; t.sh.getContext('2d').putImageData(shade, 0, 0);
    var idx = [], sum = [0, 0], wt = [0, 0], i;
    for (i = 0; i < n; i++) if (mk[4*i] || mk[4*i+1]) idx.push(i);
    t.idx = Int32Array.from(idx); t.mk = new Float32Array(idx.length * 2); t.lab = new Float32Array(idx.length * 3);
    for (var q = 0; q < idx.length; q++) {
      i = idx[q]; var l = toLab(px[4*i], px[4*i+1], px[4*i+2]);
      t.lab[3*q] = l[0]; t.lab[3*q+1] = l[1]; t.lab[3*q+2] = l[2];
      for (k = 0; k < 2; k++) { var a = mk[4*i+k] / 255; t.mk[2*q+k] = a; sum[k] += a * l[0]; wt[k] += a; }
    }
    t.Lm = [sum[0] / wt[0], sum[1] / wt[1]];
    t.cv.width = W; t.cv.height = H; t.ctx = t.cv.getContext('2d');
    t.show(0, true); t.el.classList.add('ready');
    var q2 = 1, step = function () { if (q2 < car_n(t)) { t.render(t.car.palette[q2++].hex); setTimeout(step, 30); } };
    setTimeout(step, 60);
    t.bind();
  };
  function car_n(t) { return t.car.palette.length; }
  Tile.prototype.render = function (hex) {
    var t = this, c = t.cache[hex]; if (c) return c;
    var o = new ImageData(new Uint8ClampedArray(t.base.data), t.W, t.H), px = o.data, src = t.base.data,
        tb = toLab.apply(null, hexRgb(hex)), tr = t.car.hero.roof ? toLab.apply(null, hexRgb(t.car.hero.roof)) : tb;
    for (var q = 0; q < t.idx.length; q++) {
      var i = t.idx[q], ab = t.mk[2*q], ar = t.mk[2*q+1], kk = ab >= ar ? 0 : 1, tg = kk ? tr : tb, a = kk ? ar : ab,
          dev = t.lab[3*q] - t.Lm[kk];
      dev *= dev > 0 ? Math.min(1, (100 - tg[0]) / (100 - t.Lm[kk])) : Math.min(1, tg[0] / t.Lm[kk]);
      var ly = (Math.max(0, Math.min(100, tg[0] + dev)) + 16) / 116, fx = ly + tg[1] / 500, fz = ly - tg[2] / 200,
          X = finv(fx) * WP[0], Y = finv(ly), Z = finv(fz) * WP[2];
      px[4*i]   = src[4*i]   * (1 - a) + gam(Mi[0][0]*X + Mi[0][1]*Y + Mi[0][2]*Z) * a;
      px[4*i+1] = src[4*i+1] * (1 - a) + gam(Mi[1][0]*X + Mi[1][1]*Y + Mi[1][2]*Z) * a;
      px[4*i+2] = src[4*i+2] * (1 - a) + gam(Mi[2][0]*X + Mi[2][1]*Y + Mi[2][2]*Z) * a;
    }
    c = document.createElement('canvas'); c.width = t.W; c.height = t.H; c.getContext('2d').putImageData(o, 0, 0);
    return (t.cache[hex] = c);
  };
  Tile.prototype.show = function (i, now) {
    var t = this, p = t.car.palette[i], to = t.render(p.hex), from = t.cur;
    t.i = i; t.el.style.setProperty('--tile-colour', p.hex); t.label.textContent = p.label; t.cur = to;
    cancelAnimationFrame(t.anim);
    if (now || !from || calm) { t.ctx.clearRect(0, 0, t.W, t.H); t.ctx.globalAlpha = 1; t.ctx.drawImage(to, 0, 0); return; }
    var t0 = performance.now(), dur = 380;
    (function tick(ts) {
      var k = Math.min(1, (ts - t0) / dur);
      t.ctx.clearRect(0, 0, t.W, t.H);
      t.ctx.globalAlpha = 1; t.ctx.drawImage(from, 0, 0);
      t.ctx.globalAlpha = k * k * (3 - 2 * k); t.ctx.drawImage(to, 0, 0);
      if (k < 1) t.anim = requestAnimationFrame(tick);
    })(t0);
  };
  Tile.prototype.next = function () { this.show((this.i + 1) % this.car.palette.length); };
  Tile.prototype.bind = function () {
    var t = this, el = t.el, n = t.car.palette.length;
    if (n < 2 || editing) return;
    function stop() { clearInterval(t.timer); t.timer = 0; }
    if (fine && !calm) {
      el.addEventListener('mouseenter', function () { stop(); t.next(); t.timer = setInterval(function () { t.next(); }, 1100); });
      el.addEventListener('mouseleave', function () { stop(); t.show(0); });
      el.addEventListener('focusin', function () { if (!t.timer) { t.next(); t.timer = setInterval(function () { t.next(); }, 1100); } });
      el.addEventListener('focusout', function () { stop(); t.show(0); });
    } else if (!fine) {
      // touch: tap the car for the next colour; the title and the button still open the detail page
      el.addEventListener('click', function (e) { if (!e.target.closest('a')) t.next(); });
    }
  };

  var tiles = {};
  Array.prototype.forEach.call(document.querySelectorAll('.tile'), function (el) {
    var car = CARS[el.dataset.car];
    if (!('IntersectionObserver' in window)) { tiles[car.slug] = new Tile(el, car); return; }
    var io = new IntersectionObserver(function (es) {
      if (es[0].isIntersecting) { io.disconnect(); tiles[car.slug] = new Tile(el, car); }
    }, { rootMargin: '200px' });
    io.observe(el);
  });
})();
"""


def page(cars):
    themes = sorted({c["theme"] for c in cars})
    fonts = fonts_href(themes)
    css = PAGE_CSS + "".join(theme_file(t, "tile.css") for t in themes) + offsets_css(themes)
    # the footer names the photographer/brand once ("3D Sets"), not every model ("3D Sets Model 19 Torq")
    def brand(c):
        url = urlsplit(c["hero"].get("credit_url") or "")
        return re.sub(r"\s+Model\s+\d+.*$", "", c["hero"].get("credit") or ""), f"{url.scheme}://{url.netloc}" if url.netloc else ""
    credits = sorted({brand(c) for c in cars})
    credit_html = ", ".join(
        f'<a href="{html.escape(u)}" target="_blank" rel="noopener">{html.escape(n)}</a>' for n, u in credits if n and u)
    js_cars = {c["slug"]: {"slug": c["slug"], "palette": c["palette"],
                           "hero": {"mask": c["hero"]["mask"], "roof": c["hero"].get("roof"), "cut": c["cut"], "fg": c["fg"]}} for c in cars}
    js = PAGE_JS.replace("__CARS__", json.dumps(js_cars, separators=(",", ":")).replace("</", "<\\/"))
    font_link = f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link rel="stylesheet" href="{fonts}">' if fonts else ""
    if SHOW_WORDMARK:
        font_link += '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Alfa+Slab+One&family=Pacifico&display=swap">'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Car paint filaments</title>
<meta name="description" content="Original paint colours of classic cars matched to the closest PLA, PETG and ASA filaments.">
{font_link}
<style>{css}</style>
<script>document.documentElement.className = 'js';</script>
</head>
<body>
<header class="site-head">
  {WORDMARK_HTML if SHOW_WORDMARK else "<h1>Car paint filaments</h1>"}
  <p>Original paint colours of classic cars, matched to the closest PLA, PETG and ASA filaments. Pick a car, then a filament.</p>
</header>
<main>{"".join(tile_html(c) for c in cars)}
</main>
<footer class="site-foot">
  <span>Car photos{": " + credit_html if credit_html else ""}</span>
  <span>Created by {html.escape(AUTHOR)}</span>
  {'<span class="visit-count" id="vc" hidden></span>' if config.GOATCOUNTER else ''}
</footer>
<script>{js}</script>
{counter_html()}
</body>
</html>
"""


def published_cars():
    out = []
    for car in config.list_cars():
        meta = config.car_meta(car)
        if not meta.get("publish"):
            continue
        data = config.car_data(car)
        if not (data / "matches.json").exists() or not (data / "hero.json").exists():
            print(f"! {car}: no matches.json/hero.json (a tile needs the recolor preview), skipped", file=sys.stderr)
            continue
        out.append(collect_car(car))
    return sorted(out, key=lambda c: (c["order"], c["display"].lower()))


def main():
    cars = published_cars()
    if not cars:
        sys.exit("no published car with data/hero.json")
    SITE_DIR.mkdir(exist_ok=True)
    config.write_text(SITE_DIR / "index.html", page(cars))
    for c in cars:
        print(f'{c["slug"]}: {len(c["palette"])} colours, primary {c["palette"][0]["hex"]}')
    print(f"wrote {SITE_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
