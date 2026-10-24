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

USED_THUMBS = set()     # slugs whose photo the page needs (filled while rows are built)

def filament_row(c, fil_thumbs, is_primary=False):
    cls = de_class(c["delta_e"])
    if fil_thumbs.get(c["slug"]):
        USED_THUMBS.add(c["slug"])
    full = f"{c['brand']} {c['material']} {c['color_name']}"
    # Swatch and name are both .pick: click recolours the preview, hover/focus opens the bubble (TIP_JS).
    attrs = (f'data-hex="{c["hex"]}" data-name="{esc(full)}" data-slug="{esc(c["slug"])}" '
             f'data-shop="{esc(c.get("shop") or "?")}" data-shop-cls="{slugify(c.get("shop") or "") or "unknown"}" '
             f'data-url="{esc(clean_url(c))}"')
    # One <a> around swatch + name (display: contents keeps the row's grid): hover opens the bubble, a plain
    # click recolours the preview (HERO_JS), ctrl/middle click follows the shop link.
    link = f'<a class="pick" href="{esc(clean_url(c))}" target="_blank" rel="noopener" {attrs}>'
    name = f"<strong>{esc(c['brand'])}</strong> {esc(c['material'])} <span class=\"color\">{esc(c['color_name'])}</span>"
    if is_primary:
        return f"""
      <div class="filament primary">{link}
        <div class="swatch mini" style="background:{c['hex']}"></div>
        <div class="finfo">
          <div class="fname">{name}</div>
          <div class="fsub"><span class="de {cls}">ΔE {c['delta_e']:.1f}</span></div>
        </div></a>
      </div>
    """
    return f"""
      <div class="filament alt">{link}
        <span class="swatch tiny" style="background:{c['hex']}"></span>
        <span class="fname-inline">{name}</span>
        <span class="de {cls}">ΔE {c['delta_e']:.1f}</span></a>
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
.pick { cursor: pointer; color: inherit; text-decoration: none; }
a.pick { display: contents; }
a.pick:hover .swatch, a.pick:focus-visible .swatch { outline: 2px solid var(--teal); outline-offset: 1px; }
a.pick.picked .swatch { outline: 2px solid var(--orange); outline-offset: 1px; }
/* Layout and states only: colours, borders, shadows, button faces and icons live in themes/<name>/theme.css */
.hero-preview {
  position: fixed; right: max(12px, env(safe-area-inset-right, 0px)); bottom: 12px; z-index: 20;
  width: min(270px, 52vw); padding: 10px; font-size: 0.8rem; line-height: 1.3;
}
.hero-preview canvas { display: block; width: 100%; height: auto; background: #f8f8f8; transition: opacity .15s; margin-bottom: 8px; cursor: zoom-in; }
.hero-preview canvas.swap { opacity: .55; }
.hero-preview .hp-info:empty { display: none; }
.hero-preview .t-link { display: inline-block; margin-bottom: 6px; }
.hero-preview .hp-credit { margin-top: 2px; font-family: var(--font-mono); font-size: 0.62rem; color: var(--muted); }
.hero-preview .hp-credit a { color: var(--muted); }
.hero-preview .hp-close, .hero-preview .hp-zoom {
  position: absolute; top: 12px; width: 24px; height: 24px; padding: 0; cursor: pointer;
  display: flex; align-items: center; justify-content: center; line-height: 1;
}
.hero-preview .hp-close { right: 12px; }
.hero-preview .hp-zoom  { right: 42px; }
.hero-preview.big { width: min(1000px, calc(100vw - 24px)); right: 50%; transform: translateX(50%); padding: 14px 16px 10px; }
.hero-preview.big .hp-close, .hero-preview.big .hp-zoom { top: 22px; width: 30px; height: 30px; }
.hero-preview.big .hp-close { right: 24px; } .hero-preview.big .hp-zoom { right: 62px; }
.hero-preview.big canvas { cursor: zoom-out; }
.hero-preview.big .hp-credit { letter-spacing: 0.16em; text-transform: uppercase; margin-top: 4px; }
.hero-preview.closed .hp-zoom { display: none; }
.hero-preview.closed canvas, .hero-preview.closed .hp-info { display: none; }
.hero-preview.closed { width: auto; padding: 10px 44px 8px 12px; min-height: 28px; }
.hero-preview.closed .hp-close { top: 8px; right: 8px; }
"""

HERO_HTML = """
<aside class="hero-preview" id="hero-preview" aria-label="Recolored car preview">
  <button class="hp-close" type="button" title="Hide preview" aria-label="Hide preview"></button>
  <button class="hp-zoom" type="button" title="Enlarge" aria-label="Enlarge preview"></button>
  <canvas id="hero-canvas"></canvas>
  <div class="hp-info" id="hero-info"></div>
  <div class="hp-credit">Photo: <a href="__CREDIT_URL__" target="_blank" rel="noopener">__CREDIT__</a></div>
</aside>
"""

HERO_JS = """
<script>
(function () {
  var H = __HERO__, TN = H.tone || {}, DL = TN.dl || 0, CS = TN.contrast == null ? 1 : TN.contrast;  // per-car calibration (review_hero.py /calibrate)
  var box = document.getElementById('hero-preview'), cv = document.getElementById('hero-canvas'),
      info = document.getElementById('hero-info'), ctx = cv.getContext('2d');
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

  var photo = new Image(), mask = new Image(), loaded = 0, W, Hh, base, mk, L, Lm = [0, 0], Sc = [1, 1], cur = null;
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
    // Contrast of the body shading differs a lot between photos (flat pastel Doppler vs. hard-lit Torq). Cap it at the
    // same level for every car, otherwise one filament colour looks darker or flatter on some cars than on others.
    var vr = [0, 0]; for (var j = 0; j < n; j++) for (var q = 0; q < 2; q++) { var aq = mk[4*j+q] / 255, dq = L[3*j] - Lm[q]; vr[q] += aq * dq * dq; }
    Sc = [0, 1].map(function (q) { return wt[q] > 0 ? Math.min(1, 12 / Math.sqrt(vr[q] / wt[q])) : 1; });
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
    var cs = getComputedStyle(document.documentElement), q = function (n) { return cs.getPropertyValue(n).trim(); };
    ctx.fillStyle = q('--hero-q-bg'); ctx.beginPath(); ctx.arc(x, y0, r, 0, 6.2832); ctx.fill();
    ctx.fillStyle = q('--hero-q-fg'); ctx.font = '700 ' + Math.round(r * 1.5) + 'px ' + q('--hero-q-font');
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('?', x, y0 + r * 0.06);
  }

  function render(hex) {
    var tb = toLab.apply(null, hexRgb(hex)), tr = H.roof ? toLab.apply(null, hexRgb(H.roof)) : tb,
        out = ctx.createImageData(W, Hh), o = out.data, d = base.data, n = W * Hh;
    for (var i = 0; i < n; i++) {
      var ab = mk[4*i] / 255, ar = mk[4*i+1] / 255, r = d[4*i], g = d[4*i+1], b = d[4*i+2];
      if (ab > 0 || ar > 0) {
        var kk = ab >= ar ? 0 : 1, t = kk ? tr : tb, a = kk ? ar : ab, t0 = Math.max(0, Math.min(100, t[0] + DL)), dev = (L[3*i] - Lm[kk]) * Sc[kk] * CS;
        dev *= dev > 0 ? Math.min(1, (100 - t0) / (100 - Lm[kk])) : Math.min(1, t0 / Lm[kk]);
        var ly = (Math.max(0, Math.min(100, t0 + dev)) + 16) / 116, fx = ly + t[1] / 500, fz = ly - t[2] / 200,
            X = finv(fx) * WP[0], Y = finv(ly), Z = finv(fz) * WP[2];
        r = r * (1 - a) + gam(Mi[0][0]*X + Mi[0][1]*Y + Mi[0][2]*Z) * a;
        g = g * (1 - a) + gam(Mi[1][0]*X + Mi[1][1]*Y + Mi[1][2]*Z) * a;
        b = b * (1 - a) + gam(Mi[2][0]*X + Mi[2][1]*Y + Mi[2][2]*Z) * a;
      }
      o[4*i] = r; o[4*i+1] = g; o[4*i+2] = b; o[4*i+3] = 255;
    }
    return out;
  }
  function paint(hex) { ctx.putImageData(render(hex), 0, 0); }

  // Small recoloured copy for the hover bubble: a JPEG data URL per colour, '' until the photo has loaded.
  var small = {}, off = document.createElement('canvas'), tmp = document.createElement('canvas');
  window.heroRender = function (hex) {
    if (loaded < 2) return '';
    if (small[hex]) return small[hex];
    tmp.width = W; tmp.height = Hh; tmp.getContext('2d').putImageData(render(hex), 0, 0);
    off.width = 440; off.height = Math.round(440 * Hh / W);
    off.getContext('2d').drawImage(tmp, 0, 0, off.width, off.height);
    return (small[hex] = off.toDataURL('image/jpeg', 0.85));
  };

  var picked = null;
  function pick(el) {
    cur = el.dataset.hex; info.innerHTML = window.filInfo(el.dataset);
    if (picked) picked.classList.remove('picked');
    (picked = el).classList.add('picked');
    box.classList.remove('closed');
    if (loaded < 2) return;
    cv.classList.add('swap');
    setTimeout(function () { paint(cur); cv.classList.remove('swap'); }, 60);
  }
  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest('.pick');
    if (el && !(e.ctrlKey || e.metaKey || e.shiftKey || e.button)) { e.preventDefault(); pick(el); }
  });
  document.addEventListener('keydown', function (e) {
    var el = e.target.classList && e.target.classList.contains('pick') ? e.target : null;
    if (el && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); pick(el); }
  });
})();
</script>
"""

TIP_CSS = """
.fil-tip { position: fixed; z-index: 30; width: 220px; padding: 10px; display: none; font-size: 0.8rem; line-height: 1.3; }
.fil-tip.show { display: block; }
.fil-tip img { display: block; width: 100%; height: 140px; object-fit: cover; margin-bottom: 8px; }
.fil-tip img.t-car { height: auto; object-fit: contain; background: #f8f8f8; }
.fil-tip .t-name, .hero-preview .t-name { font-weight: 600; margin-bottom: 6px; }
.fil-tip .t-row, .hero-preview .t-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-family: var(--font-mono); }
.fil-tip .t-sw, .hero-preview .t-sw { width: 16px; height: 16px; flex: none; }
.fil-tip .t-link, .hero-preview .t-link { font-weight: 600; text-decoration: none; }
.fil-tip .t-link:hover, .hero-preview .t-link:hover { text-decoration: underline; }
"""

TIP_JS = """
<script>
(function () {
  var T = __THUMBS__, tip = document.createElement('div'), cur = null, timer = null;
  tip.className = 'fil-tip'; tip.setAttribute('role', 'tooltip'); document.body.appendChild(tip);
  // Name / HEX / shop / link block, shared with the hover bubble (TIP_JS).
  window.filInfo = function (d) {
    function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
    return '<div class="t-name">' + esc(d.name) + '</div>' +
      '<div class="t-row"><span class="t-sw" style="background:' + esc(d.hex) + '"></span>' + esc(d.hex) + '</div>' +
      '<div class="t-row"><span class="shop-tag shop-' + esc(d.shopCls) + '">' + esc(d.shop) + '</span></div>' +
      (d.url && d.url !== '#' ? '<a class="t-link" href="' + esc(d.url) + '" target="_blank" rel="noopener">Open in shop ↗</a>' : '');
  };
  function show(el) {
    clearTimeout(timer); if (cur === el && tip.classList.contains('show')) return; cur = el;
    var d = el.dataset, car = window.heroRender ? window.heroRender(d.hex) : '', src = car || T[d.slug],
        img = src ? '<img alt=""' + (car ? ' class="t-car"' : '') + ' src="' + src + '">' : '';
    tip.innerHTML = img + window.filInfo(d);
    tip.classList.add('show');
    var r = (el.querySelector('.fname, .fname-inline') || el).getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight,
        x = Math.min(Math.max(8, r.left), innerWidth - w - 8),
        y = r.bottom + 6; if (y + h > innerHeight - 8) y = Math.max(8, r.top - h - 6);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  function hide() { timer = setTimeout(function () { tip.classList.remove('show'); cur = null; }, 180); }
  document.addEventListener('mouseover', function (e) {
    var el = e.target.closest && e.target.closest('.pick'); if (el && el.dataset.slug) show(el);
  });
  document.addEventListener('mouseout', function (e) {
    var el = e.target.closest && e.target.closest('.pick'); if (el && el.dataset.slug) hide();
  });
  document.addEventListener('focusin', function (e) { if (e.target.dataset && e.target.dataset.slug) show(e.target); });
  document.addEventListener('focusout', hide);
  tip.addEventListener('mouseenter', function () { clearTimeout(timer); });
  tip.addEventListener('mouseleave', hide);
  document.addEventListener('click', function (e) {          // touch: tap opens it, tap elsewhere closes it
    var el = e.target.closest && e.target.closest('.pick');
    if (el && el.dataset.slug) show(el); else if (!tip.contains(e.target)) tip.classList.remove('show');
  });
  addEventListener('scroll', function () { tip.classList.remove('show'); }, {passive: true});
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

# The floating back-to-top button: position and show/hide are shared, the look is each theme's `.to-top` rule.
TOP_CSS = """
html { scroll-behavior: smooth; }
.to-top { position: fixed; left: max(12px, env(safe-area-inset-left, 0px)); bottom: 12px; z-index: 19;
  display: inline-flex; align-items: center; justify-content: center;
  transition: opacity .2s, visibility .2s, transform .08s, box-shadow .08s, background .15s; }
.to-top span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.js .to-top { opacity: 0; visibility: hidden; }
.js .to-top.show { opacity: 1; visibility: visible; }
"""
TOP_JS = ("(function(){var b=document.querySelector('.to-top');if(!b)return;document.documentElement.classList.add('js');"
          "function f(){b.classList.toggle('show',window.scrollY>600)}addEventListener('scroll',f,{passive:true});f();})();")

def load_theme(name):
    """(css, fonts query, header motif html) from themes/<name>/. Each car picks one in car.json."""
    d = config.THEMES / name
    if not (d / "theme.css").is_file():
        sys.exit(f"theme '{name}' not found: expected {d}/theme.css")
    def part(f):
        fp = d / f
        return fp.read_text().strip() if fp.is_file() else ""
    return part("theme.css"), part("fonts.txt"), part("motif.html")

def region_css(regions):
    """Show only the active region's candidates and counts (body[data-region])."""
    out = ["[data-r] { display: none; }"]
    for r in regions:
        out.append(f'body[data-region="{r}"] div[data-r="{r}"] {{ display: block; }}')
        out.append(f'body[data-region="{r}"] .rcols[data-r="{r}"] {{ display: contents; }}')
    return "\n".join(out)

REGION_SWITCH_CSS = """
.region-switch button { font: inherit; cursor: pointer; }
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
    theme_css, fonts_q, motif_html = load_theme(meta.get("theme", "doppler"))

    by_name = {r: {m["name"]: m for m in matches_by_region[r]} for r in regions}
    by_year = {}
    for m in matches:
        if m.get("year") is None:
            print(f"! {m['name']}: no year, left out of the page")
            continue
        by_year.setdefault(m["year"], []).append(m)
    total_count = sum(len(v) for v in by_year.values())

    USED_THUMBS.clear()
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
        switch = ('<div class="year-nav region-switch"><span class="nav-label">Shops in:</span>'
                  + "".join(f'<button type="button" data-region-btn="{r}" aria-pressed="{"true" if r == regions[0] else "false"}">{esc(labels[r])}</button>'
                            for r in regions)
                  + '</div>')

    _years = sorted(by_year.keys())
    _year_range = f"{_years[0]}-{_years[-1]}" if _years else ""
    _year_links = sorted(by_year.keys(), reverse=True)
    hero_css, hero_html, hero_js = hero_parts(hero)
    tip_js = TIP_JS.replace("__THUMBS__", json.dumps({k: fil_thumbs[k] for k in sorted(USED_THUMBS)}).replace("</", "<\\/"))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{esc(DISPLAY)} · {_year_range} color card</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<style>
{theme_css}
{TOP_CSS}
{REGION_SWITCH_CSS}
{region_css(regions)}
{hero_css}
{TIP_CSS}
</style>

<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{esc(fonts_q)}&display=swap">
</head>
<body id="top" data-region="{regions[0]}">

<div class="paper">

<header class="page-head">
  {motif_html}
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
<a class="to-top" href="#top" aria-label="Back to top"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 3.5 12.5H9V21h6v-8.5h5.5z"/></svg><span>Back to top</span></a>
<script>{TOP_JS}</script>
{hero_html}
{hero_js}
{tip_js}
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
