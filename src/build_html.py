"""Build HTML page — all car colors × filament matches, retro styling.

Writes `cars/<car>/output/<car>.html` (cz library) or `<car>-intl.html`.

Usage:
    python build_html.py [--car <name>] [--library cz|intl]
"""
import argparse, json, re, sys, html as html_mod
from datetime import date
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import config
from shoplib import slugify

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
# codes (FilamentColors.xyz buy links do). Shortener links hide the code in the
# redirect, so they fall back to the swatch page on FilamentColors.xyz.
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
        return f"https://filamentcolors.xyz/swatch/{c['slug']}/"
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

def load_theme(name):
    """(css, fonts query, header motif html) from themes/<name>/. Each car picks one in car.json."""
    d = config.THEMES / name
    if not (d / "theme.css").is_file():
        sys.exit(f"theme '{name}' not found: expected {d}/theme.css")
    def part(f):
        fp = d / f
        return fp.read_text().strip() if fp.is_file() else ""
    return part("theme.css"), part("fonts.txt"), part("motif.html")

def render(car, library, matches, fil_thumbs, all_filaments, meta, hero=None):
    """The whole self-contained page as a string."""
    DISPLAY    = meta.get("display", car.title())
    SCRIPT_TAG = meta.get("script_tagline", "")
    BADGE_TOP  = meta.get("badge_label", DISPLAY.upper())
    theme_css, fonts_q, motif_html = load_theme(meta.get("theme", "doppler"))

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
            rows.append(f"""
        <article class="row">
          <div class="col paint-col">{paint_block(m)}</div>
          <div class="col pla-col">{filament_column(m['pla'], 'PLA', fil_thumbs)}</div>
          <div class="col petg-col">{filament_column(m['petg'], 'PETG', fil_thumbs)}</div>
        </article>
        """)

    pla_n  = sum(1 for f in all_filaments if f["material"] in config.PLA_MATERIALS and f.get("rgb"))
    petg_n = sum(1 for f in all_filaments if f["material"] in config.PETG_MATERIALS and f.get("rgb"))
    shops  = sorted({f.get("shop","?") for f in all_filaments if f.get("rgb")})

    _years = sorted(by_year.keys())
    _year_range = f"{_years[0]}-{_years[-1]}" if _years else ""
    _year_links = sorted(by_year.keys(), reverse=True)
    _title_suffix = " color card" if library == "cz" else " · intl library"
    hero_css, hero_html, hero_js = hero_parts(hero)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{esc(DISPLAY)} · {_year_range}{_title_suffix}</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<style>
{theme_css}
{hero_css}
</style>

<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{esc(fonts_q)}&display=swap">
</head>
<body>

<div class="paper">

<header class="page-head">
  {motif_html}
  <div class="hero-top"><span>Factory Paint Archive · {_year_range}</span></div>
  <h1>{esc(DISPLAY)}</h1>
  <span class="script">{esc(SCRIPT_TAG)}</span>
  <div class="meta-grid">
    <div><strong>{total_count}</strong><span>factory colors</span></div>
    <div><strong>{pla_n}</strong><span>PLA candidates</span></div>
    <div><strong>{petg_n}</strong><span>PETG candidates</span></div>
    <div><strong>{len(shops)}</strong><span>e-shops</span></div>
    <div><strong>{len(by_year)}</strong><span>model years</span></div>
  </div>
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
</body>
</html>
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    ap.add_argument("--library", default="cz", choices=["cz", "intl"])
    args = ap.parse_args()

    car_data = config.car_data(args.car)
    matches  = json.loads((car_data / f"matches_{args.library}.json").read_text(encoding="utf-8"))
    thumbs   = json.loads((car_data / f"thumbnails_{args.library}.json").read_text(encoding="utf-8"))
    all_filaments = [f for f in json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8"))
                     if f.get("library", "cz") == args.library]
    hero_path = car_data / "hero.json"
    hero = json.loads(hero_path.read_text(encoding="utf-8")) if hero_path.exists() else None
    page = render(args.car, args.library, matches, thumbs["filaments"], all_filaments,
                  config.car_meta(args.car), hero)

    out = config.car_output(args.car) / (f"{args.car}.html" if args.library == "cz" else f"{args.car}-{args.library}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(out, page)
    print(f"HTML: {out} ({out.stat().st_size/1024:.1f} KB)")

if __name__ == "__main__":
    main()
