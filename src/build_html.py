"""Build HTML page — all car colors × filament matches, retro styling.

Writes `cars/<car>/output/<car>.html`, one page with a switch between regions.

Usage:
    python build_html.py [--car <name>]
"""
import argparse, json, re, sys, html as html_mod
from datetime import date
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import config
from shoplib import slugify, region_labels

NO_MATCH_DE = 12.0      # primary at or above this gets the "no close match" banner

def de_class(dE):
    if dE < 2: return "exc"
    if dE < 4: return "vg"
    if dE < 7: return "ok"
    if dE < NO_MATCH_DE: return "weak"
    return "bad"

def esc(s): return html_mod.escape(str(s))

def paint_block(h):
    poly = ' <span class="chip">metallic</span>' if h.get("poly") else ""
    # No link to the card source: pages don't name or link the card library (the data keeps source_url).
    year = f'<span class="year">{esc(h["year"])}</span>'
    return f"""
      <div class="paint">
        <div class="swatch big" style="background:{h['hex']}"></div>
        <div class="meta">
          <div class="name">{esc(h['name'])}{poly}</div>
          <div class="sub">
            {year}
            · {esc(h['car_code'])}
            · ref. {esc(h['paint_ref'])}
          </div>
          <div class="hex">{h['hex']} <span class="rgb">RGB {h['rgb'][0]},{h['rgb'][1]},{h['rgb'][2]}</span></div>
        </div>
      </div>
    """

def shop_tag(shop):
    sl = slugify(shop or "") or "unknown"
    return f'<span class="shop-tag shop-{sl}">{esc(shop or "?")}</span>'

# Shop links in the published page must not carry anyone's affiliate or tracking
# codes. Shortener links hide the code in the redirect, so they (and unsafe links)
# become a dead "#" rather than a tracked link.
SHORTENERS = {"amzn.to", "collabs.shop", "bit.ly", "geni.us", "shrsl.com", "tinyurl.com"}
TRACKING_PARAMS = re.compile(r"^(utm_.*|aff.*|a_aid|a_bid|ref|ref_|tag|ascsubtag|linkcode|linkid|camp|creative|creativeasin|ie"
                             r"|sca_ref|srsltid|gclid|fbclid|mc_.*|_pos|_psq|_ss|_v|_sid|variant_tracking)$", re.I)

def safe_url(url):
    """Only http(s) links reach the page (third-party data could carry javascript: etc.)."""
    return urlsplit(url or "").scheme in ("http", "https")

def clean_url(c):
    url = c.get("url") or ""
    parts = urlsplit(url)
    if not safe_url(url) or parts.hostname in SHORTENERS:
        return "#"
    path = re.sub(r"/ref=[^/]*", "", parts.path)          # amazon /ref=… path segments
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not TRACKING_PARAMS.match(k)])
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))

def filament_row(c, fil_thumbs, is_primary=False):
    cls = de_class(c["delta_e"])
    tsrc = fil_thumbs.get(c["slug"], "")
    sw_cls = "mini" if is_primary else "tiny"
    thumb = f'<img class="fil-thumb" src="{tsrc}" alt="">' if tsrc and is_primary else ""
    name = f"<strong>{esc(c['brand'])}</strong> {esc(c['material'])} <span class=\"color\">{esc(c['color_name'])}</span>"
    if is_primary:
        return f"""
      <div class="filament primary">
        <div class="swatch {sw_cls} pick" role="button" tabindex="0" data-hex="{c['hex']}" data-name="{esc(c['brand'])} {esc(c['material'])} {esc(c['color_name'])}" style="background:{c['hex']}"></div>
        <div class="finfo">
          <div class="fname">{name}</div>
          <div class="fsub">
            <span class="hex">{c['hex']}</span>
            <span class="de {cls}">ΔE {c['delta_e']:.1f}</span>
            {shop_tag(c.get('shop'))}
          </div>
          <a class="shop" href="{esc(clean_url(c))}" target="_blank" rel="noopener">Open ↗</a>
          {thumb}
        </div>
      </div>
    """
    return f"""
      <div class="filament alt">
        <span class="swatch {sw_cls} pick" role="button" tabindex="0" data-hex="{c['hex']}" data-name="{esc(c['brand'])} {esc(c['material'])} {esc(c['color_name'])}" style="background:{c['hex']}"></span>
        <span class="fname-inline">{name}</span>
        <span class="hex">{c['hex']}</span>
        <span class="de {cls}">ΔE {c['delta_e']:.1f}</span>
        {shop_tag(c.get('shop'))}
        <a class="shop-arrow" href="{esc(clean_url(c))}" target="_blank" rel="noopener">↗</a>
      </div>
    """

def filament_column(cands, kind, fil_thumbs):
    if not cands:
        return f'<div class="col-label">{kind}</div><div class="filament empty">no {kind} candidate</div>'
    out = [f'<div class="col-label">{kind}</div>']
    primary = cands[0]
    if primary["delta_e"] >= NO_MATCH_DE:
        out.append(f'<div class="no-match">No close match: the best {kind} is ΔE {primary["delta_e"]:.1f} away</div>')
    out.append(filament_row(primary, fil_thumbs, is_primary=True))
    # Alternatives: up to 4 more, only good matches (ΔE < 10) or ones close to the primary
    threshold = max(10.0, primary["delta_e"] + 2.0)
    alts = [c for c in cands[1:5] if c["delta_e"] < threshold]
    for c in alts:
        out.append(filament_row(c, fil_thumbs, is_primary=False))
    return "".join(out)


HERO_CSS = """
.pick { cursor: pointer; }
.pick:hover, .pick:focus-visible { outline: 2px solid var(--teal); outline-offset: 1px; }
.pick.picked { outline: 2px solid var(--orange); outline-offset: 1px; }
.hero-preview {
  position: fixed; right: max(12px, env(safe-area-inset-right, 0px)); bottom: 12px; z-index: 20;
  width: min(340px, 52vw); background: var(--bg-raised);
  border: 1px solid var(--rule); box-shadow: 0 2px 0 var(--rule), 0 8px 24px rgba(45,34,23,0.22);
  padding: 8px 8px 6px;
}
.hero-preview canvas { display: block; width: 100%; height: auto; background: #f8f8f8; transition: opacity .15s; }
.hero-preview canvas.swap { opacity: .55; }
.hero-preview .hp-name { font-size: 0.74rem; margin-top: 5px; min-height: 1.1em; }
.hero-preview .hp-credit { font-family: var(--font-mono); font-size: 0.62rem; color: var(--muted); }
.hero-preview .hp-credit a { color: var(--muted); }
/* Retro push buttons: cream face, navy rim, hard offset shadow like the year badge */
.hero-preview .hp-close, .hero-preview .hp-zoom {
  position: absolute; top: 12px; width: 24px; height: 24px; padding: 0;
  display: flex; align-items: center; justify-content: center;
  border: 1.5px solid var(--navy); border-radius: 50%; cursor: pointer;
  font-family: var(--font-display); font-size: 0.8rem; line-height: 1; color: var(--navy);
  box-shadow: 1.5px 1.5px 0 var(--navy); transition: transform .08s, box-shadow .08s;
}
.hero-preview .hp-close { right: 12px; background: var(--orange-weak); }
.hero-preview .hp-zoom  { right: 42px; background: var(--mustard-weak); }
.hero-preview .hp-close:hover, .hero-preview .hp-zoom:hover { background: var(--mustard); }
.hero-preview .hp-close:active, .hero-preview .hp-zoom:active { transform: translate(1.5px, 1.5px); box-shadow: 0 0 0 var(--navy); }
.hero-preview .hp-close:focus-visible, .hero-preview .hp-zoom:focus-visible { outline: 2px solid var(--teal); outline-offset: 2px; }
.hero-preview.big .hp-close, .hero-preview.big .hp-zoom { top: 22px; width: 30px; height: 30px; font-size: 1rem; }
.hero-preview.big .hp-close { right: 24px; } .hero-preview.big .hp-zoom { right: 62px; }
.hero-preview canvas { cursor: zoom-in; }
.hero-preview.big {
  width: min(1000px, calc(100vw - 24px)); right: 50%; transform: translateX(50%);
  box-shadow: 0 0 0 100vmax rgba(45,34,23,0.45), 0 8px 24px rgba(45,34,23,0.3);
}
.hero-preview.big canvas { cursor: zoom-out; }
.hero-preview.big { padding: 14px 16px 10px; outline: 1px solid var(--rule); outline-offset: -7px; }
.hero-preview.big .hp-name {
  font-family: var(--font-display); font-size: 1.15rem; line-height: 1.2; letter-spacing: 0.02em;
  color: var(--teal-deep); text-shadow: 1px 1px 0 var(--orange-weak); margin-top: 10px;
}
.hero-preview.big .hp-credit {
  font-size: 0.7rem; letter-spacing: 0.16em; text-transform: uppercase; margin-top: 4px;
}
.hero-preview.closed .hp-zoom { display: none; }
.hero-preview.closed canvas, .hero-preview.closed .hp-name { display: none; }
.hero-preview.closed { width: auto; padding: 10px 44px 8px 12px; min-height: 28px; }
.hero-preview.closed .hp-close { top: 8px; right: 8px; }
"""

HERO_HTML = """
<aside class="hero-preview" id="hero-preview" aria-label="Recolored car preview">
  <button class="hp-close" type="button" title="Hide preview" aria-label="Hide preview">✕</button>
  <button class="hp-zoom" type="button" title="Enlarge" aria-label="Enlarge preview">⤢</button>
  <canvas id="hero-canvas"></canvas>
  <div class="hp-name" id="hero-name"></div>
  <div class="hp-credit">Photo: <a href="__CREDIT_URL__" target="_blank" rel="noopener">__CREDIT__</a></div>
</aside>
"""

HERO_JS = """
<script>
(function () {
  var H = __HERO__;
  var box = document.getElementById('hero-preview'), cv = document.getElementById('hero-canvas'),
      label = document.getElementById('hero-name'), ctx = cv.getContext('2d');
  box.querySelector('.hp-close').onclick = function () { box.classList.remove('big'); box.classList.toggle('closed'); };
  function zoom() { box.classList.toggle('big'); }
  box.querySelector('.hp-zoom').onclick = zoom; cv.onclick = zoom;
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') box.classList.remove('big'); });
  var M = [[0.4124564,0.3575761,0.1804375],[0.2126729,0.7151522,0.0721750],[0.0193339,0.1191920,0.9503041]];
  var Mi = [[3.2404542,-1.5371385,-0.4985314],[-0.9692660,1.8760108,0.0415560],[0.0556434,-0.2040259,1.0572252]];
  var WP = [0.95047, 1, 1.08883];
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

  var photo = new Image(), mask = new Image(), loaded = 0, W, Hh, base, mk, L, Lm = [0, 0], cur = null;
  function ready() {
    if (++loaded < 2) return;
    W = cv.width = photo.width; Hh = cv.height = photo.height;
    ctx.drawImage(photo, 0, 0); base = ctx.getImageData(0, 0, W, Hh);
    ctx.clearRect(0, 0, W, Hh); ctx.drawImage(mask, 0, 0); mk = ctx.getImageData(0, 0, W, Hh).data;
    var n = W * Hh, lab = new Float32Array(n * 3), sum = [0, 0], wt = [0, 0], d = base.data;
    for (var i = 0; i < n; i++) {
      var c = toLab(d[4*i], d[4*i+1], d[4*i+2]); lab[3*i] = c[0]; lab[3*i+1] = c[1]; lab[3*i+2] = c[2];
      for (var k = 0; k < 2; k++) { var a = mk[4*i+k] / 255; sum[k] += a * c[0]; wt[k] += a; }
    }
    L = lab; Lm = [sum[0] / wt[0], sum[1] / wt[1]];
    if (cur) paint(cur); else greyed();
  }
  photo.onload = mask.onload = ready; photo.src = H.photo; mask.src = H.mask;

  function greyed() {
    var g = ctx.createImageData(W, Hh), o = g.data, d = base.data;
    for (var i = 0; i < W * Hh * 4; i += 4) {
      var y = 0.3 * d[i] + 0.59 * d[i+1] + 0.11 * d[i+2];
      o[i] = o[i+1] = o[i+2] = 255 - (255 - y) * 0.7; o[i+3] = 255;
    }
    ctx.putImageData(g, 0, 0);
    var r = Hh * 0.2, x = W / 2, y0 = Hh / 2;
    ctx.fillStyle = 'rgba(45,34,23,0.72)'; ctx.beginPath(); ctx.arc(x, y0, r, 0, 6.2832); ctx.fill();
    ctx.fillStyle = '#fffdf4'; ctx.font = '700 ' + Math.round(r * 1.5) + 'px Georgia, serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('?', x, y0 + r * 0.06);
  }

  function paint(hex) {
    var tb = toLab.apply(null, hexRgb(hex)), tr = H.roof ? toLab.apply(null, hexRgb(H.roof)) : tb,
        out = ctx.createImageData(W, Hh), o = out.data, d = base.data, n = W * Hh;
    for (var i = 0; i < n; i++) {
      var ab = mk[4*i] / 255, ar = mk[4*i+1] / 255, r = d[4*i], g = d[4*i+1], b = d[4*i+2];
      if (ab > 0 || ar > 0) {
        var kk = ab >= ar ? 0 : 1, t = kk ? tr : tb, a = kk ? ar : ab, dev = L[3*i] - Lm[kk];
        dev *= dev > 0 ? Math.min(1, (100 - t[0]) / (100 - Lm[kk])) : Math.min(1, t[0] / Lm[kk]);
        var ly = (Math.max(0, Math.min(100, t[0] + dev)) + 16) / 116, fx = ly + t[1] / 500, fz = ly - t[2] / 200,
            X = finv(fx) * WP[0], Y = finv(ly), Z = finv(fz) * WP[2];
        r = r * (1 - a) + gam(Mi[0][0]*X + Mi[0][1]*Y + Mi[0][2]*Z) * a;
        g = g * (1 - a) + gam(Mi[1][0]*X + Mi[1][1]*Y + Mi[1][2]*Z) * a;
        b = b * (1 - a) + gam(Mi[2][0]*X + Mi[2][1]*Y + Mi[2][2]*Z) * a;
      }
      o[4*i] = r; o[4*i+1] = g; o[4*i+2] = b; o[4*i+3] = 255;
    }
    ctx.putImageData(out, 0, 0);
  }

  var picked = null;
  function pick(el) {
    cur = el.dataset.hex; label.textContent = el.dataset.name + ' · ' + cur;
    if (picked) picked.classList.remove('picked');
    (picked = el).classList.add('picked');
    box.classList.remove('closed');
    if (loaded < 2) return;
    cv.classList.add('swap');
    setTimeout(function () { paint(cur); cv.classList.remove('swap'); }, 60);
  }
  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest('.pick');
    if (el) pick(el);
  });
  document.addEventListener('keydown', function (e) {
    var el = e.target.classList && e.target.classList.contains('pick') ? e.target : null;
    if (el && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); pick(el); }
  });
})();
</script>
"""

def hero_parts(hero):
    """(css, html, js) for the recolor preview; empty strings when the car has no hero."""
    if not hero:
        return "", "", ""
    html = (HERO_HTML.replace("__CREDIT__", esc(hero.get("credit") or "source"))
                     .replace("__CREDIT_URL__", esc(hero["credit_url"]) if safe_url(hero.get("credit_url", "")) else "#"))
    js = HERO_JS.replace("__HERO__", json.dumps({k: hero.get(k) for k in ("photo", "mask", "roof")}).replace("</", "<\\/"))
    return HERO_CSS, html, js

# SVG starburst — mid-century atomic motif
STARBURST = '''<svg class="starburst" viewBox="-50 -50 100 100" aria-hidden="true">
  <g fill="currentColor">
    <polygon points="0,-46 3,-10 46,0 3,10 0,46 -3,10 -46,0 -3,-10"/>
    <polygon points="32,-32 7,-7 32,32 -7,7 -32,32 -7,-7 -32,-32 7,7" opacity="0.7"/>
  </g>
  <circle cx="0" cy="0" r="4" fill="currentColor"/>
</svg>'''

def region_css(regions):
    """Show only the active region's candidates and counts (body[data-region])."""
    out = ["[data-r] { display: none; }"]
    for r in regions:
        out.append(f'body[data-region="{r}"] div[data-r="{r}"] {{ display: block; }}')
        out.append(f'body[data-region="{r}"] .rcols[data-r="{r}"] {{ display: contents; }}')
    return "\n".join(out)

REGION_SWITCH_CSS = """
.region-switch { display: flex; gap: 8px; align-items: center; justify-content: center; margin: 22px 0 0; flex-wrap: wrap; }
.region-switch .nav-label { color: var(--muted); letter-spacing: 0.12em; text-transform: uppercase; font-size: 0.68rem; font-family: var(--font-mono); }
.region-switch button {
  font-family: var(--font-mono); font-size: 0.8rem; letter-spacing: 0.1em; text-transform: uppercase;
  padding: 6px 14px; background: var(--bg-raised); color: var(--fg); border: 1px solid var(--rule); cursor: pointer;
}
.region-switch button:hover { border-color: var(--orange-deep); }
.region-switch button[aria-pressed="true"] { background: var(--orange); color: #fff; border-color: var(--orange-deep); }
"""

REGION_JS = """
<script>
(function () {
  var btns = document.querySelectorAll('[data-region-btn]');
  function show(r, keep) {
    document.body.dataset.region = r;
    btns.forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.regionBtn === r ? 'true' : 'false'); });
    if (!keep) { try { var u = new URL(location.href); u.searchParams.set('region', r); history.replaceState(null, '', u); } catch (e) {} }
  }
  btns.forEach(function (b) { b.onclick = function () { show(b.dataset.regionBtn); }; });
  var want = null;
  try { want = new URL(location.href).searchParams.get('region'); } catch (e) {}
  if (want && document.querySelector('[data-region-btn="' + want + '"]')) show(want, true);
})();
</script>
"""

def render(car, matches_by_region, fil_thumbs, all_filaments, meta, hero=None):
    """The whole self-contained page as a string. `matches_by_region` is {region: [match, ...]}."""
    labels  = region_labels()
    regions = [r for r in labels if r in matches_by_region]
    matches = matches_by_region[regions[0]]          # same colours in every region
    DISPLAY    = meta.get("display", car.title())
    SCRIPT_TAG = meta.get("script_tagline", "")
    BADGE_TOP  = meta.get("badge_label", DISPLAY.upper())

    by_name = {r: {m["name"]: m for m in matches_by_region[r]} for r in regions}
    by_year = {}
    for m in matches:
        if m.get("year") is None:
            print(f"! {m['name']}: no year, left out of the page")
            continue
        by_year.setdefault(m["year"], []).append(m)
    total_count = sum(len(v) for v in by_year.values())

    rows = []
    for year in sorted(by_year.keys(), reverse=True):
        rows.append(f"""
      <h2 class="year-head" id="y{year}">
        <span class="year-badge">
          <span class="year-badge-top">{BADGE_TOP}</span>
          <span class="year-badge-num">{year}</span>
        </span>
        <span class="year-tagline">Model Year</span>
      </h2>""")
        for m in by_year[year]:
            cols = "".join(f"""
          <div class="rcols" data-r="{r}">
            <div class="col pla-col">{filament_column(by_name[r][m['name']]['pla'], 'PLA', fil_thumbs)}</div>
            <div class="col petg-col">{filament_column(by_name[r][m['name']]['petg'], 'PETG', fil_thumbs)}</div>
          </div>""" for r in regions)
            rows.append(f"""
        <article class="row">
          <div class="col paint-col">{paint_block(m)}</div>{cols}
        </article>
        """)

    counts = ""
    for r in regions:
        fr = [f for f in all_filaments if r in (f.get("regions") or []) and f.get("rgb")]
        pla_n  = sum(1 for f in fr if f["material"] in config.PLA_MATERIALS)
        petg_n = sum(1 for f in fr if f["material"] in config.PETG_MATERIALS)
        shops  = {f.get("shop", "?") for f in fr}
        counts += (f'<div data-r="{r}"><strong>{pla_n}</strong><span>PLA candidates</span></div>'
                   f'<div data-r="{r}"><strong>{petg_n}</strong><span>PETG candidates</span></div>'
                   f'<div data-r="{r}"><strong>{len(shops)}</strong><span>e-shops</span></div>')
    switch = ""
    if len(regions) > 1:
        switch = ('<div class="region-switch"><span class="nav-label">Shops in:</span>'
                  + "".join(f'<button type="button" data-region-btn="{r}" aria-pressed="{"true" if r == regions[0] else "false"}">{esc(labels[r])}</button>'
                            for r in regions)
                  + '</div>')

    _years = sorted(by_year.keys())
    _year_range = f"{_years[0]}-{_years[-1]}" if _years else ""
    _year_links = sorted(by_year.keys(), reverse=True)
    hero_css, hero_html, hero_js = hero_parts(hero)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{esc(DISPLAY)} · {_year_range} color card</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<style>
/* Mid-century reproduction of a factory color-chip card.
   Cream paper ground, bottle-teal + sunburst-orange + mustard accents, slab serif display. */
:root {{
  --bg: #fefaeb;
  --bg-paper: #fffdf4;
  --bg-raised: #fffffb;
  --fg: #2d2217;
  --muted: #7a6a53;
  --rule: #d7c7a3;
  --rule-soft: #e7d8b4;

  --teal: #0f8f8a;         /* tortoise / bottle teal (hero sign) */
  --teal-deep: #0a6361;
  --teal-weak: #c7e7e5;
  --orange: #e36b2a;       /* sunburst orange */
  --orange-deep: #b24a12;
  --orange-weak: #ffd6b5;
  --mustard: #e9a73a;      /* banana-split mustard */
  --mustard-weak: #f6dca2;
  --cherry: #c73932;       /* '53 lipstick red */
  --navy: #27394e;         /* 1952 Broadway Blue */

  --good: #2b7a4b;
  --warn: #a56114;
  --bad: #a3281f;

  --font-display: "Alfa Slab One", "Rockwell", Georgia, serif;
  --font-script:  "Yesteryear", "Pacifico", cursive;
  --font-mono:    "Space Mono", ui-monospace, "SF Mono", Menlo, monospace;
  color-scheme: light;
  --font-body:    "Fraunces", "Inter", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
}}
body {{
  background: var(--bg);
  background-image:
    repeating-linear-gradient(45deg, transparent 0 26px, color-mix(in srgb, var(--mustard) 3%, transparent) 26px 27px),
    repeating-linear-gradient(-45deg, transparent 0 26px, color-mix(in srgb, var(--teal) 2%, transparent) 26px 27px);
  color: var(--fg); font-family: var(--font-body);
  line-height: 1.45; max-width: 1360px; margin: 0 auto;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 28px;
  font-variant-numeric: tabular-nums;
}}

.paper {{
  background: var(--bg-paper);
  border: 1px solid var(--rule);
  box-shadow: 0 2px 0 var(--rule), 0 6px 22px rgba(45,34,23,0.12);
  padding: 28px clamp(18px, 3vw, 36px);
  position: relative;
}}
.paper::before, .paper::after {{
  content: ""; position: absolute; width: 11px; height: 11px;
  border-radius: 999px; background: var(--bg); border: 1px solid var(--rule);
  top: 60px;
}}
.paper::before {{ left: -5px; box-shadow: 0 110px 0 var(--bg), 0 110px 0 1px var(--rule), 0 220px 0 var(--bg), 0 220px 0 1px var(--rule); }}
.paper::after {{ right: -5px; box-shadow: 0 110px 0 var(--bg), 0 110px 0 1px var(--rule), 0 220px 0 var(--bg), 0 220px 0 1px var(--rule); }}

/* ===== Hero ===== */
header.page-head {{ position: relative; padding-bottom: 24px; margin-bottom: 24px;
  border-bottom: 3px double var(--rule); }}
.hero-top {{
  display: flex; gap: 10px; align-items: center;
  font-family: var(--font-mono); font-size: 0.72rem;
  letter-spacing: 0.22em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 6px;
}}
.hero-top::before, .hero-top::after {{
  content: ""; flex: 1; height: 1px;
  background: repeating-linear-gradient(90deg, var(--rule) 0 6px, transparent 6px 10px);
}}

h1 {{
  font-family: var(--font-display); font-weight: 400;
  font-size: clamp(2rem, 4.6vw + 0.6rem, 3.8rem);
  margin: 2px 0 0; line-height: 1.02; letter-spacing: 0.01em;
  color: var(--teal-deep); text-wrap: balance;
  text-shadow: 2px 2px 0 var(--orange-weak), 4px 4px 0 var(--mustard);
}}

.script {{
  display: inline-block; margin-top: 22px;
  font-family: var(--font-script); font-size: clamp(1.4rem, 2.6vw + 0.3rem, 2.2rem);
  color: var(--orange); line-height: 1; transform: rotate(-3deg);
}}
.script::after {{
  content: ""; display: block; width: 80%; height: 6px; margin: 2px 0 0 10%;
  background: var(--orange); border-radius: 50%;
  mask: radial-gradient(ellipse at center, black 55%, transparent 60%);
  -webkit-mask: radial-gradient(ellipse at center, black 55%, transparent 60%);
}}

.starburst {{
  width: 72px; height: 72px; color: var(--orange);
  position: absolute; top: 6px; right: 8px;
  filter: drop-shadow(2px 2px 0 var(--mustard));
}}

/* ===== Stats strip ===== */
.meta-grid {{
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px; margin: 22px 0 0;
}}
.meta-grid > div {{
  background: var(--bg-raised); border: 1px solid var(--rule);
  padding: 10px 12px; text-align: center;
  box-shadow: 2px 2px 0 var(--rule-soft);
}}
.meta-grid > div strong {{
  display: block; font-family: var(--font-display); font-weight: 400;
  font-size: 1.9rem; line-height: 1; color: var(--teal-deep);
}}
.meta-grid > div span {{
  font-family: var(--font-mono); font-size: 0.68rem; letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--muted);
}}

{REGION_SWITCH_CSS}
{region_css(regions)}

/* ===== Year nav ===== */
.year-nav {{
  display: flex; flex-wrap: wrap; gap: 6px 8px; margin: 20px 0 0;
  align-items: center; font-family: var(--font-mono); font-size: 0.78rem;
}}
.year-nav .nav-label {{ color: var(--muted); letter-spacing: 0.12em; text-transform: uppercase; font-size: 0.68rem; }}
.year-nav a {{
  padding: 3px 12px; background: var(--mustard); color: #2d2217;
  text-decoration: none; font-weight: 600;
  border: 1px solid var(--mustard); border-radius: 999px;
  box-shadow: 1px 1px 0 var(--orange-deep);
}}
.year-nav a:hover {{ background: var(--orange); color: #fff; border-color: var(--orange-deep); }}

/* ===== Legend ===== */
.legend {{
  display: flex; flex-wrap: wrap; gap: 12px 14px; align-items: center;
  padding: 12px 14px; background: var(--bg-raised);
  border: 1px solid var(--rule); border-radius: 0;
  margin: 20px 0; font-size: 0.78rem;
  box-shadow: 3px 3px 0 var(--rule-soft);
}}
.legend .lblock {{ display: inline-flex; gap: 5px; align-items: center; }}
.legend .legend-head {{ font-family: var(--font-display); font-size: 0.95rem; color: var(--teal-deep); letter-spacing: 0.02em; }}
.pill, .de {{
  padding: 1px 8px; border-radius: 999px; font-weight: 600;
  font-family: var(--font-mono); font-size: 0.72rem;
}}
.pill.exc, .de.exc  {{ background: color-mix(in srgb, var(--good) 20%, transparent); color: var(--good); border: 1px solid var(--good); }}
.pill.vg,  .de.vg   {{ background: color-mix(in srgb, var(--teal) 20%, transparent); color: var(--teal-deep); border: 1px solid var(--teal); }}
.pill.ok,  .de.ok   {{ background: color-mix(in srgb, var(--mustard) 28%, transparent); color: var(--warn); border: 1px solid var(--mustard); }}
.pill.weak,.de.weak {{ background: #88888822; color: var(--muted); border: 1px solid #8888887a; }}
.pill.bad, .de.bad  {{ background: color-mix(in srgb, var(--cherry) 20%, transparent); color: var(--bad); border: 1px solid var(--cherry); }}

/* ===== Shop tags ===== */
.shop-tag {{
  display: inline-block; font-family: var(--font-mono); font-size: 0.66rem;
  padding: 1px 7px; border-radius: 3px; letter-spacing: 0.04em;
  background: var(--rule-soft); color: var(--muted); font-weight: 600;
}}
.shop-tag.shop-smart3d {{ background: var(--teal-weak); color: var(--teal-deep); }}
.shop-tag.shop-prusa3d {{ background: var(--orange-weak); color: var(--orange-deep); }}
.shop-tag.shop-3djake  {{ background: var(--mustard-weak); color: var(--warn); }}
.shop-tag.shop-aurapol {{ background: color-mix(in srgb, var(--cherry) 15%, transparent); color: var(--bad); }}
.shop-tag.shop-fillamentum {{ background: color-mix(in srgb, #6b3fa0 15%, transparent); color: #6b3fa0; }}
.shop-tag.shop-filamentpm {{ background: color-mix(in srgb, #2d7f3f 15%, transparent); color: #2d7f3f; }}
.shop-tag.shop-na3d {{ background: color-mix(in srgb, #0066a3 15%, transparent); color: #0066a3; }}
.shop-tag.shop-hubacek3d {{ background: color-mix(in srgb, #8a5a2b 15%, transparent); color: #8a5a2b; }}
.shop-tag.shop-3dfox {{ background: color-mix(in srgb, #c4561a 15%, transparent); color: #c4561a; }}
.shop-tag.shop-bambu-lab {{ background: color-mix(in srgb, #00ae42 15%, transparent); color: #007a2e; }}
/* ===== Year section header — mid-century "DAL card" styling ===== */
h2.year-head {{
  display: flex; align-items: center; gap: 14px;
  margin: 36px 0 14px; padding: 0;
  border: none; scroll-margin-top: 10px;
  font-weight: 400;
}}
.year-badge {{
  display: inline-flex; flex-direction: column; align-items: center;
  background: var(--navy); color: #fdf7e4;
  padding: 6px 18px 8px; border-radius: 4px;
  box-shadow: 3px 3px 0 var(--orange), 3px 3px 0 1px var(--orange-deep);
  letter-spacing: 0.02em; line-height: 1;
}}
.year-badge-top {{
  font-family: var(--font-mono); font-size: 0.68rem;
  letter-spacing: 0.3em; opacity: 0.85; margin-bottom: 2px;
}}
.year-badge-num {{
  font-family: var(--font-display); font-size: 1.9rem; line-height: 1;
}}
.year-tagline {{
  font-family: var(--font-script); font-size: 1.3rem;
  color: var(--teal-deep); transform: rotate(-2deg); line-height: 1;
}}
/* ===== Table rows ===== */
.row {{
  display: grid; grid-template-columns: 1fr 1.1fr 1.1fr; gap: 16px;
  padding: 16px 0; border-bottom: 1px dashed var(--rule); align-items: start;
}}
.row:last-of-type {{ border-bottom: none; }}
@media (max-width: 900px) {{ .row {{ grid-template-columns: 1fr; }} }}

.col-label {{
  font-family: var(--font-mono); font-size: 0.66rem; letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--muted); margin: 0 0 6px 2px;
}}

/* ===== Paint block — mimics a paint-chip card ===== */
.paint {{ display: flex; gap: 12px; align-items: flex-start; min-width: 0; }}
.paint .swatch.big {{
  width: 88px; height: 88px; flex-shrink: 0;
  border: 2px solid var(--bg-paper);
  outline: 1px solid var(--rule);
  box-shadow: 3px 3px 0 var(--rule-soft);
  border-radius: 2px;
}}
.paint .meta {{ min-width: 0; flex: 1; }}
.paint .name {{
  font-family: var(--font-display); font-weight: 400;
  font-size: 1.05rem; line-height: 1.2; color: var(--fg);
  letter-spacing: 0.005em;
}}
.paint .sub {{
  font-family: var(--font-mono); font-size: 0.72rem;
  color: var(--muted); margin-top: 3px; letter-spacing: 0.02em;
}}
.paint .year {{ color: var(--orange-deep); font-weight: 600; }}
.paint a.year {{ text-decoration: none; border-bottom: 1px dotted var(--orange-deep); }}
.paint a.year:hover {{ border-bottom-style: solid; }}

.no-match {{
  margin: 0 0 6px; padding: 5px 10px;
  background: color-mix(in srgb, var(--cherry) 12%, transparent);
  border: 1px solid var(--cherry); border-left: 4px solid var(--cherry);
  color: var(--bad); font-family: var(--font-mono); font-size: 0.72rem; font-weight: 600;
  border-radius: 2px;
}}
.paint .hex {{ font-family: var(--font-mono); font-size: 0.78rem; margin-top: 4px; }}
.paint .rgb {{ color: var(--muted); font-size: 0.7rem; margin-left: 4px; }}

.chip {{
  display: inline-block; padding: 1px 7px; border-radius: 999px;
  font-family: var(--font-mono); font-size: 0.64rem; letter-spacing: 0.06em;
  text-transform: uppercase; background: var(--mustard); color: #2d2217;
  font-weight: 600; margin-left: 6px; vertical-align: middle;
}}

/* ===== Primary filament card ===== */
.filament.primary {{
  display: grid; grid-template-columns: 48px 1fr; gap: 12px;
  padding: 10px 12px;
  background: var(--bg-raised);
  border: 1px solid var(--rule); border-left: 4px solid var(--teal);
  margin-bottom: 6px; border-radius: 2px;
  box-shadow: 2px 2px 0 var(--rule-soft);
}}
.filament.primary .swatch.mini {{
  width: 48px; height: 48px; border-radius: 2px;
  border: 2px solid var(--bg-paper);
  outline: 1px solid var(--rule);
}}
.filament.primary .fname {{ font-size: 0.9rem; line-height: 1.3; }}
.filament.primary .fname strong {{ font-family: var(--font-display); font-weight: 400; font-size: 0.98rem; }}
.filament.primary .fname .color {{ color: var(--muted); font-size: 0.82rem; }}
.filament.primary .fsub {{
  display: flex; flex-wrap: wrap; gap: 5px 8px; align-items: center;
  margin-top: 4px; font-size: 0.74rem; font-family: var(--font-mono);
}}
.filament.primary .hex {{ color: var(--muted); }}
.filament.primary .shop {{
  display: inline-block; margin-top: 4px;
  color: var(--orange-deep); text-decoration: none;
  font-family: var(--font-mono); font-size: 0.74rem; font-weight: 600;
  letter-spacing: 0.03em;
}}
.filament.primary .shop:hover {{ text-decoration: underline; }}
.filament.primary .fil-thumb {{
  display: block; margin-top: 8px; width: 64px; height: 64px;
  object-fit: cover; border: 1px solid var(--rule); border-radius: 2px;
  filter: sepia(0.05);
}}

/* Alt row — compact */
.filament.alt {{
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto auto auto auto;
  gap: 5px 7px; align-items: center;
  padding: 5px 10px; font-size: 0.76rem;
  border-bottom: 1px solid var(--rule-soft);
}}
.filament.alt:last-child {{ border-bottom: none; }}
.filament.alt .swatch.tiny {{
  width: 18px; height: 18px; border-radius: 2px;
  border: 1px solid var(--rule);
}}
.filament.alt .fname-inline {{
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 0.78rem;
}}
.filament.alt .fname-inline .color {{ color: var(--muted); font-size: 0.72rem; }}
.filament.alt .hex {{ font-family: var(--font-mono); color: var(--muted); font-size: 0.72rem; }}
.filament.alt .shop-arrow {{
  color: var(--orange-deep); text-decoration: none; font-weight: 700;
  padding: 0 4px; font-size: 0.9rem;
}}
.filament.alt .shop-arrow:hover {{ text-decoration: underline; }}
.filament.empty {{ color: var(--muted); font-style: italic; padding: 8px 10px; }}

/* ===== Phones: the colour name gets the full line, the rest wraps below it ===== */
@media (max-width: 600px) {{
  .paper {{ padding: 20px 14px; }}
  .paint .swatch.big {{ width: 64px; height: 64px; }}
  .filament.primary {{ grid-template-columns: 40px minmax(0, 1fr); gap: 10px; }}
  .filament.primary .swatch.mini {{ width: 40px; height: 40px; }}
  .filament.alt {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px 7px; }}
  .filament.alt .fname-inline {{
    flex: 1 1 calc(100% - 28px); white-space: normal; overflow: visible; text-overflow: clip;
    font-size: 0.86rem; line-height: 1.25;
  }}
  .filament.alt .hex {{ margin-left: 25px; }}
}}
/* ===== Notes block ===== */
/* ===== Footer ===== */
footer.card-footer {{
  margin-top: 20px; padding-top: 18px;
  border-top: 3px double var(--rule); text-align: center;
}}
footer.card-footer .brand {{
  font-family: var(--font-display); font-size: 1.1rem;
  color: var(--teal-deep); letter-spacing: 0.08em;
}}
footer.card-footer .sub {{
  font-family: var(--font-mono); font-size: 0.72rem;
  color: var(--muted); letter-spacing: 0.14em;
  text-transform: uppercase; margin-top: 4px;
}}

a {{ color: var(--teal-deep); }}
img {{ max-width: 100%; }}
{hero_css}
</style>

<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Alfa+Slab+One&family=Yesteryear&family=Pacifico&family=Space+Mono:wght@400;700&family=Fraunces:ital,wght@0,400;0,500;0,600;1,400&display=swap">
</head>
<body data-region="{regions[0]}">

<div class="paper">

<header class="page-head">
  {STARBURST}
  <div class="hero-top"><span>Factory Paint Archive · {_year_range}</span></div>
  <h1>{esc(DISPLAY)}</h1>
  <span class="script">{esc(SCRIPT_TAG)}</span>
  <div class="meta-grid">
    <div><strong>{total_count}</strong><span>factory colors</span></div>
    {counts}
    <div><strong>{len(by_year)}</strong><span>model years</span></div>
  </div>
  {switch}
  <nav class="year-nav">
    <span class="nav-label">Jump to year:</span>
    {''.join(f'<a href="#y{y}">{y}</a>' for y in _year_links)}
  </nav>
</header>

<div class="legend">
  <span class="legend-head">ΔE2000 scale</span>
  <span class="lblock"><span class="pill exc">&lt; 2</span> excellent</span>
  <span class="lblock"><span class="pill vg">2-4</span> very good</span>
  <span class="lblock"><span class="pill ok">4-7</span> good</span>
  <span class="lblock"><span class="pill weak">7-12</span> noticeable shift</span>
  <span class="lblock"><span class="pill bad">&gt; 12</span> large difference</span>
</div>

<main>
  {''.join(rows)}
</main>

<footer class="card-footer">
  <div class="brand">{esc(DISPLAY)} factory colors · 3D-print filament matches</div>
  <div class="sub">Generated by car-paint-filaments · {_year_range} color cards · {date.today().year}</div>
</footer>

</div>
{hero_html}
{hero_js}
{REGION_JS if len(regions) > 1 else ""}
</body>
</html>
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    args = ap.parse_args()

    car_data = config.car_data(args.car)
    matches  = json.loads((car_data / "matches.json").read_text(encoding="utf-8"))
    thumbs   = json.loads((car_data / "thumbnails.json").read_text(encoding="utf-8"))
    all_filaments = json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8"))
    hero_path = car_data / "hero.json"
    hero = json.loads(hero_path.read_text(encoding="utf-8")) if hero_path.exists() else None
    page = render(args.car, matches, thumbs["filaments"], all_filaments, config.car_meta(args.car), hero)

    out = config.car_output(args.car) / f"{args.car}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(out, page)
    print(f"HTML: {out} ({out.stat().st_size/1024:.1f} KB)")

if __name__ == "__main__":
    main()
