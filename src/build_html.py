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
from shoplib import slugify, region_labels, finish_names
import compute_matches
from tile_parts import head_card_html, TILE_BASE_CSS

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
            {f"· ref. {esc(h['paint_ref'])}" if h.get("paint_ref") else ""}
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
             f'data-brand="{esc(c["brand"])}" data-material="{esc(c["material"])}" data-color="{esc(c["color_name"])}" '
             f'data-shop="{esc(c.get("shop") or "?")}" data-shop-cls="{slugify(c.get("shop") or "") or "unknown"}" '
             f'data-url="{esc(clean_url(c))}"' + (' data-neon="1"' if c.get("neon") else "") + (f' data-finish="{esc(" ".join(c["finish"]))}"' if c.get("finish") else ""))
    # One <a> around swatch + name (display: contents keeps the row's grid): hover opens the bubble, a plain
    # click recolours the preview (HERO_JS), ctrl/middle click follows the shop link.
    link = f'<a class="pick" href="{esc(clean_url(c))}" target="_blank" rel="noopener" {attrs}>'
    name = f"<strong>{esc(c['brand'])}</strong> {esc(c['material'])} <span class=\"color\">{esc(c['color_name'])}</span>"
    neon = ' <span class="neon-tag" title="Neon / fluorescent: ranked behind normal filaments">NEON</span>' if c.get("neon") else ""
    neon += "".join(f' <span class="finish-tag" title="{esc(f)} finish">{esc(f.upper())}</span>' for f in c.get("finish") or ())
    name += neon
    if is_primary:
        # Three lines: brand / filament / match (ΔE, HEX). The shop opens from the swatch/name of the hover bubble and the preview.
        return f"""
      <div class="filament primary">{link}
        <div class="swatch mini" style="background:{c['hex']}"></div>
        <div class="finfo">
          <div class="fname"><strong>{esc(c['brand'])}</strong><span class="fline">{esc(c['material'])} <span class="color">{esc(c['color_name'])}</span>{neon}</span></div>
        </div></a>
        <div class="fsub"><span class="de {cls}">ΔE {c['delta_e']:.1f}</span><span class="fhex">{c['hex'].upper()}</span></div>
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


# Candidate rows: the swatch-and-name link is layout-transparent, so swatch, name and ΔE line sit in the row's grid.
# Always included: a car without a recolor preview (no hero) needs it as much as one with.
PICK_CSS = """
.pick { cursor: pointer; color: inherit; text-decoration: none; }
a.pick { display: contents; }
a.pick:hover .swatch, a.pick:focus-visible .swatch { outline: 2px solid var(--teal); outline-offset: 1px; }
a.pick.picked .swatch { outline: 2px solid var(--orange); outline-offset: 1px; }
div.filament.primary { row-gap: 0; }
div.filament.primary .swatch.mini { grid-row: 1 / 3; align-self: start; }
div.filament.primary .finfo { grid-column: 2; grid-row: 1; }
div.filament.primary .fsub { grid-column: 2; grid-row: 2; margin-top: 3px; }
.filament.primary .fname strong, .filament.primary .fline { display: block; }
.filament.primary .fhex { color: var(--muted); }
"""

HERO_CSS = """
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
.hero-preview.big { width: min(900px, calc(100vw - 24px), calc((100vh - 290px) * 1.5625)); right: 50%; bottom: 50%; transform: translate(50%, 50%); padding: 14px 16px 10px; }
.hero-preview.big .hp-close, .hero-preview.big .hp-zoom { top: 22px; width: 30px; height: 30px; }
.hero-preview.big .hp-close { right: 24px; } .hero-preview.big .hp-zoom { right: 62px; }
.hero-preview.big canvas { cursor: zoom-out; }
.hero-preview.big .hp-credit { letter-spacing: 0.16em; text-transform: uppercase; margin-top: 4px; }
.hero-preview.empty .hp-zoom { display: none; }
.hero-preview.empty canvas { cursor: default; }
.hero-preview.closed { display: none; }
"""

HERO_HTML = """
<aside class="hero-preview empty" id="hero-preview" aria-label="Recolored car preview">
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
  var H = __HERO__, Z = H.zones, TN = H.tone || {}, DL = TN.dl || 0, CS = TN.contrast == null ? 1 : TN.contrast;  // per-car calibration (review_hero.py /calibrate)
  var box = document.getElementById('hero-preview'), cv = document.getElementById('hero-canvas'),
      info = document.getElementById('hero-info'), ctx = cv.getContext('2d');
  box.querySelector('.hp-close').onclick = function () { box.classList.remove('big'); box.classList.add('closed'); };
  function zoom() { if (!box.classList.contains('empty')) box.classList.toggle('big'); }
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

  var photo = new Image(), mask = new Image(), loaded = 0, W, Hh, base, mk, L, Lm = [], Sc = [], sel = null, picks = [], last = null;
  function za(i, z) { var a = 0; Z[z].channels.forEach(function (c) { a += mk[4*i+c]; }); return Math.min(1, a / 255); }
  function ready() {
    if (++loaded < 2) return;
    W = cv.width = photo.width; Hh = cv.height = photo.height;
    ctx.drawImage(photo, 0, 0); base = ctx.getImageData(0, 0, W, Hh);
    ctx.clearRect(0, 0, W, Hh); ctx.drawImage(mask, 0, 0); mk = ctx.getImageData(0, 0, W, Hh).data;
    var n = W * Hh, nz = Z.length, lab = new Float32Array(n * 3), sum = [], wt = [], d = base.data;
    for (var k0 = 0; k0 < nz; k0++) { sum.push(0); wt.push(0); }
    for (var i = 0; i < n; i++) {
      var c = toLab(d[4*i], d[4*i+1], d[4*i+2]); lab[3*i] = c[0]; lab[3*i+1] = c[1]; lab[3*i+2] = c[2];
      if (mk[4*i] | mk[4*i+1] | mk[4*i+2]) for (var k = 0; k < nz; k++) { var a = za(i, k); sum[k] += a * c[0]; wt[k] += a; }
    }
    L = lab; Lm = sum.map(function (v, k) { return wt[k] > 0 ? v / wt[k] : 50; });
    // The paintable body zones (not `fixed`, e.g. Doppler's upper and lower body) are one paint: share one mean lightness,
    // so the same colour gets the same tonal curve on all of them. Per-zone means made the shaded lower body squash its
    // highlights (less headroom) while keeping its dark tail, so it looked darker and denser than the upper body.
    var gs = 0, gw = 0, grp = [];
    Z.forEach(function (zc, k) { if (!zc.fixed && wt[k] > 0) { gs += sum[k]; gw += wt[k]; grp.push(k); } });
    if (grp.length > 1) grp.forEach(function (k) { Lm[k] = gs / gw; });
    // Contrast of the body shading differs a lot between photos (flat pastel Doppler vs. hard-lit Torq). Cap it at the
    // same level for every car, otherwise one filament colour looks darker or flatter on some cars than on others.
    var vr = Z.map(function () { return 0; });
    for (var j = 0; j < n; j++) if (mk[4*j] | mk[4*j+1] | mk[4*j+2]) for (var q = 0; q < nz; q++) { var aq = za(j, q), dq = L[3*j] - Lm[q]; vr[q] += aq * dq * dq; }
    Sc = Z.map(function (_, q) { return wt[q] > 0 ? Math.min(1, 12 / Math.sqrt(vr[q] / wt[q])) : 1; });
    if (grp.length > 1) { var gv = 0; grp.forEach(function (k) { gv += vr[k]; }); grp.forEach(function (k) { Sc[k] = Math.min(1, 12 / Math.sqrt(gv / gw)); }); }
    if (sel) paint(sel); else greyed();
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

  // hx = one hex per zone. A pixel takes the mix of the colours of the zones whose mask covers it, so soft edges
  // between two zones (upper / lower body) leave no seam of the old paint.
  function render(hx) {
    var T = hx.map(function (h) { return h ? toLab.apply(null, hexRgb(h)) : null; }), nz = Z.length,
        out = ctx.createImageData(W, Hh), o = out.data, d = base.data, n = W * Hh, acc = [0, 0, 0];
    for (var i = 0; i < n; i++) {
      var r = d[4*i], g = d[4*i+1], b = d[4*i+2];
      if (mk[4*i] | mk[4*i+1] | mk[4*i+2]) {
        var sa = 0; acc[0] = acc[1] = acc[2] = 0;
        for (var z = 0; z < nz; z++) {
          var a = za(i, z); if (a <= 0 || !T[z]) continue;
          var t = T[z], zc = Z[z], t0 = Math.max(0, Math.min(100, t[0] + DL + (zc.dl || 0))), dev = (L[3*i] - Lm[z]) * Sc[z] * CS * (zc.contrast == null ? 1 : zc.contrast);
          dev *= dev > 0 ? Math.min(1, (100 - t0) / (100 - Lm[z])) : Math.min(1, t0 / Lm[z]);
          var ly = (Math.max(0, Math.min(100, t0 + dev)) + 16) / 116, fx = ly + t[1] / 500, fz = ly - t[2] / 200,
              X = finv(fx) * WP[0], Y = finv(ly), Z3 = finv(fz) * WP[2];
          acc[0] += a * gam(Mi[0][0]*X + Mi[0][1]*Y + Mi[0][2]*Z3);
          acc[1] += a * gam(Mi[1][0]*X + Mi[1][1]*Y + Mi[1][2]*Z3);
          acc[2] += a * gam(Mi[2][0]*X + Mi[2][1]*Y + Mi[2][2]*Z3);
          sa += a;
        }
        if (sa > 0) { var A = Math.min(1, sa); r = r * (1 - A) + acc[0] / sa * A; g = g * (1 - A) + acc[1] / sa * A; b = b * (1 - A) + acc[2] / sa * A; }
      }
      o[4*i] = r; o[4*i+1] = g; o[4*i+2] = b; o[4*i+3] = 255;
    }
    return out;
  }
  function paint(hx) { ctx.putImageData(render(hx), 0, 0); }

  // One colour per zone (slot). A pick without a slot button goes to every zone; zones with `fixed` (Doppler's roof) go back to
  // their own colour then and only take a filament when its slot button is used.
  function allHex(hex) { return Z.map(function (z) { return z.fixed ? H.roof : hex; }); }
  var slots = Z.filter(function (z) { return z.label; });

  // Small recoloured copy for the hover bubble: a JPEG data URL per colour, '' until the photo has loaded.
  var small = {}, off = document.createElement('canvas'), tmp = document.createElement('canvas');
  window.heroRender = function (hex) {
    if (loaded < 2) return '';
    if (small[hex]) return small[hex];
    tmp.width = W; tmp.height = Hh; tmp.getContext('2d').putImageData(render(allHex(hex)), 0, 0);
    off.width = 440; off.height = Math.round(440 * Hh / W);
    off.getContext('2d').drawImage(tmp, 0, 0, off.width, off.height);
    return (small[hex] = off.toDataURL('image/jpeg', 0.85));
  };
  // "Put on:" buttons for the hover bubble, only for cars with more than one slot.
  window.heroSlots = function () {
    if (slots.length < 2) return '';
    return '<div class="t-slots"><span class="t-slots-l">Put on</span>' + slots.map(function (z) {
      return '<button type="button" class="t-slot" data-zone="' + z.id + '">' + z.label + '</button>'; }).join('') + '</div>';
  };
  // What the preview names: one filament block per slot (a roof only once it was set by hand), each a link to the shop;
  // a car with a single colour shows just the filament.
  function infoHtml() {
    if (slots.length < 2) return last ? window.filInfo(last, true) : '';
    return slots.map(function (z) {
      var k = Z.indexOf(z); return picks[k] ? '<div class="hp-slotblock"><div class="t-slotname">' + z.label + '</div>' + window.filInfo(picks[k], true) + '</div>' : '';
    }).join('');
  }
  function snap(d) { var c = {}; for (var key in d) c[key] = d[key]; return c; }

  var picked = null;
  function pick(el, zid) {
    var d = el.dataset;
    if (!sel) { sel = Z.map(function (z) { return z.fixed ? H.roof : null; }); picks = Z.map(function () { return null; }); }
    Z.forEach(function (z, k) {
      if (zid ? z.id === zid : true) {
        if (!zid && z.fixed) { sel[k] = H.roof; picks[k] = null; } else { sel[k] = d.hex; picks[k] = snap(d); }
      }
    });
    last = snap(d); info.innerHTML = infoHtml();
    if (picked) picked.classList.remove('picked');
    (picked = el).classList.add('picked');
    box.classList.remove('closed', 'empty');
    if (loaded < 2) return;
    cv.classList.add('swap');
    setTimeout(function () { paint(sel); cv.classList.remove('swap'); }, 60);
  }
  // A factory combination: the best PLA filament of each of its two colours goes to the upper and lower slot (the roof
  // keeps its colour), the rows of its colours are marked and every other row is hidden.
  function bestPick(name, year) {
    var row = document.querySelector('article.row[data-paint="' + name.replace(/"/g, '\\"') + '"][data-year="' + year + '"]');
    return row ? row.querySelector('.rcols[data-r="' + document.body.dataset.region + '"][data-f~="' + document.body.dataset.finish + '"] .pla-col a.pick') : null;
  }
  // A combination can use colours whose chips are on another year's card (1957 -> 1956 Frost White): its rows are marked
  // wherever they are and every other row of the page is hidden, so the page shows just the colours of the clicked two-tone.
  // Hiding or showing rows above the clicked strip would move it, so the scroll position is corrected (keepPos).
  function marks() {
    var on = document.querySelector('.combo.on');
    document.querySelectorAll('article.row').forEach(function (r) {
      var hit = on && [['upper', 'upperYear'], ['lower', 'lowerYear']].some(function (k) {
        return r.dataset.paint === on.dataset[k[0]] && r.dataset.year === on.dataset[k[1]]; });
      r.classList.toggle('combo-hit', !!hit); r.classList.toggle('combo-out', !!(on && !hit));
      if (hit && window.openRow) window.openRow(r);
    });
  }
  function zl(id) { var z = Z.filter(function (x) { return x.id === id; })[0]; return z && z.label || id; }
  function comboSel(up, lo) {
    return Z.map(function (z, k) {       // slots other than upper / lower (the roof) keep what they have: white until set by hand
      var el = z.id === 'upper' ? up : z.id === 'lower' ? lo : null;
      return el ? el.dataset.hex : ((sel && sel[k]) || (z.fixed ? H.roof : null));
    });
  }
  // For the hover bubble of a two-tone: both filaments and the car painted with them.
  window.comboInfo = function (btn) {
    var up = bestPick(btn.dataset.upper, btn.dataset.upperYear), lo = bestPick(btn.dataset.lower, btn.dataset.lowerYear);
    if (!up || !lo) return null;
    var key = 'c' + up.dataset.hex + lo.dataset.hex, src = '';
    if (loaded >= 2) {
      if (!small[key]) {
        tmp.width = W; tmp.height = Hh; tmp.getContext('2d').putImageData(render(comboSel(up, lo)), 0, 0);
        off.width = 480; off.height = Math.round(480 * Hh / W);
        off.getContext('2d').drawImage(tmp, 0, 0, off.width, off.height);
        small[key] = off.toDataURL('image/jpeg', 0.85);
      }
      src = small[key];
    }
    return { up: up, lo: lo, src: src, upLabel: zl('upper'), loLabel: zl('lower') };
  };
  function keepPos(strip, fn) {
    var t = strip.getBoundingClientRect().top; fn();
    var d = strip.getBoundingClientRect().top - t; if (d) window.scrollBy({ top: d, behavior: 'instant' });
  }
  document.addEventListener('click', function (e) {
    var cb = e.target.closest && e.target.closest('.combo');
    if (cb && cb.classList.contains('on')) { cb.classList.remove('on'); keepPos(cb.closest('.combos'), marks); return; }   // again = all colours
    if (cb) {
      var up = bestPick(cb.dataset.upper, cb.dataset.upperYear), lo = bestPick(cb.dataset.lower, cb.dataset.lowerYear);
      if (up && lo) {
        if (!sel) { sel = Z.map(function (z) { return z.fixed ? H.roof : null; }); picks = Z.map(function () { return null; }); }
        Z.forEach(function (z, k) {
          var el = z.id === 'upper' ? up : z.id === 'lower' ? lo : null;       // the roof stays as it is
          if (el) { sel[k] = el.dataset.hex; picks[k] = snap(el.dataset); }
        });
        last = snap(up.dataset); info.innerHTML = infoHtml();
        box.classList.remove('closed', 'empty');
        if (loaded >= 2) paint(sel);
      }
      var strip = cb.closest('.combos'); document.querySelectorAll('.combo.on').forEach(function (x) { x.classList.remove('on'); });
      cb.classList.add('on'); keepPos(strip, marks);
    }
  });
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('.t-slot');
    if (b) { var el0 = window.tipEl && window.tipEl(); if (el0) pick(el0, b.dataset.zone); }
  });
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
.neon-tag, .finish-tag { display: inline-block; padding: 0 4px; border: 1px solid var(--rule); color: var(--muted); font: 600 0.62rem/1.4 var(--font-mono); letter-spacing: 0.04em; vertical-align: 1px; }
.fil-tip { position: fixed; z-index: 30; width: min(340px, calc(100vw - 16px)); padding: 12px; display: none; font-size: 0.8rem; line-height: 1.3; }
.fil-tip.show { display: block; }
.fil-tip img { display: block; width: 100%; height: 200px; object-fit: cover; margin-bottom: 10px; }
.fil-tip img.t-car { height: auto; object-fit: contain; background: #f8f8f8; }
a.t-shop { display: contents; color: inherit; text-decoration: none; }
a.t-shop:hover .fname { text-decoration: underline; }
.fil-tip .filament.primary, .hero-preview .filament.primary { margin-bottom: 0; }
.t-combo { margin-bottom: 4px; }
.t-slotname { margin: 10px 0 2px; font-family: var(--font-mono); font-size: 0.66rem; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); }
.fil-tip .t-name, .hero-preview .t-name { font-weight: 600; margin-bottom: 6px; }
.fil-tip .t-row, .hero-preview .t-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-family: var(--font-mono); }
.fil-tip .t-sw, .hero-preview .t-sw { width: 16px; height: 16px; flex: none; }
.fil-tip .t-link, .hero-preview .t-link { font-weight: 600; text-decoration: none; }
.fil-tip .t-link:hover, .hero-preview .t-link:hover { text-decoration: underline; }
.hero-preview .t-row .t-shop { display: inline-flex; align-items: center; gap: 8px; }
.combos { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; margin: 4px 0 14px; font-size: 0.72rem; }
.combos-l { font-family: var(--font-mono); font-size: 0.68rem; color: var(--muted); margin-right: 4px; }
.combo { display: inline-flex; align-items: center; gap: 3px; padding: 2px 5px; font: inherit; color: inherit; background: transparent; border: 1px solid var(--rule); cursor: pointer; }
.combo:hover, .combo:focus-visible, .combo.on { background: var(--rule); }
.cb-code { font-family: var(--font-mono); font-size: 0.64rem; }
.cb-sw { display: inline-block; width: 14px; height: 14px; border: 1px solid var(--rule); }
.combos-hint { display: none; margin-left: 6px; font-size: 0.66rem; color: var(--muted); }
.combos:has(.combo.on) .combos-hint { display: inline; }
article.row.combo-hit { box-shadow: inset 3px 0 0 var(--orange); margin-left: -16px; padding-left: 16px; }   /* the line sits in the margin, the content stays where it was */
article.row.combo-out { display: none; }
.t-slots { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-top: 8px; }
.t-slots-l { font-family: var(--font-mono); font-size: 0.68rem; color: var(--muted); margin-right: 2px; }
.t-slot { font: inherit; font-size: 0.72rem; padding: 2px 7px; border: 1px solid var(--rule); background: transparent; color: inherit; cursor: pointer; }
.t-slot:hover, .t-slot:focus-visible { background: var(--rule); }
.hero-preview .t-slotname { margin: 8px 0 2px; }
.hero-preview .hp-slotblock:first-child .t-slotname { margin-top: 0; }
.hero-preview.big .hp-info { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 0 16px; }   /* enlarged: the slots side by side */
.hero-preview.big .t-slotname { margin-top: 0; }
"""

TIP_JS = """
<script>
(function () {
  var T = __THUMBS__, tip = document.createElement('div'), cur = null, timer = null;
  tip.className = 'fil-tip'; tip.setAttribute('role', 'tooltip'); document.body.appendChild(tip);
  // Brand / material / colour block, built from the same markup as a filament on the page so every theme styles it alike.
  // The swatch and the name are the link to the shop (hover bubble, combination bubble and preview alike).
  window.filInfo = function (d, linked) {
    function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
    var url = d.url && d.url !== '#' ? d.url : '', neon = (d.neon ? ' <span class="neon-tag">NEON</span>' : '') +
          (d.finish || '').split(' ').filter(Boolean).map(function (f) { return ' <span class="finish-tag">' + esc(f.toUpperCase()) + '</span>'; }).join(''),
        inner = '<div class="swatch mini" style="background:' + esc(d.hex) + '"></div><div class="finfo"><div class="fname"><strong>' + esc(d.brand) +
          '</strong><span class="fline">' + esc(d.material) + ' <span class="color">' + esc(d.color) + '</span>' + neon + '</span></div></div>';
    if (url) inner = '<a class="t-shop" href="' + esc(url) + '" target="_blank" rel="noopener">' + inner + '</a>';
    return '<div class="filament primary">' + inner + '<div class="fsub"><span class="fhex">' + esc(d.hex).toUpperCase() + '</span>' +
      '<span class="shop-tag shop-' + esc(d.shopCls) + '">' + esc(d.shop) + '</span></div></div>';
  };
  function place(r) {
    var w = tip.offsetWidth, h = tip.offsetHeight, x = Math.min(Math.max(8, r.left), innerWidth - w - 8),
        y = r.bottom + 6;
    if (y + h > innerHeight - 8) { y = r.top - h - 6; if (y < 8) y = Math.max(8, innerHeight - h - 8); }
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
    tip.querySelectorAll('img').forEach(function (i) { if (!i.complete) i.onload = function () { place(r); }; });   // the photo changes the height
  }
  // Hovering a factory two-tone: the car in that combination and the filament chosen for each of its two colours.
  function showCombo(btn) {
    clearTimeout(timer); var c = window.comboInfo && window.comboInfo(btn); if (!c) return; cur = btn;
    tip.innerHTML = (c.src ? '<img class="t-car" alt="" src="' + c.src + '">' : '') +
      '<div class="t-combo"><strong>' + btn.querySelector('.cb-code').textContent + '</strong> ' + btn.title + '</div>' +
      '<div class="t-slotname">' + c.upLabel + '</div>' + window.filInfo(c.up.dataset) +
      '<div class="t-slotname">' + c.loLabel + '</div>' + window.filInfo(c.lo.dataset);
    tip.classList.add('show'); place(btn.getBoundingClientRect());
  }
  function show(el) {
    clearTimeout(timer); if (cur === el && tip.classList.contains('show')) return; cur = el;
    var d = el.dataset, car = window.heroRender ? window.heroRender(d.hex) : '', src = car || T[d.slug],
        img = src ? '<img alt=""' + (car ? ' class="t-car"' : '') + ' src="' + src + '">' : '';
    tip.innerHTML = img + window.filInfo(d) + (window.heroSlots ? window.heroSlots() : '');
    tip.classList.add('show'); place((el.querySelector('.fname, .fname-inline') || el).getBoundingClientRect());
  }
  window.tipEl = function () { return cur; };
  function hide() { timer = setTimeout(function () { tip.classList.remove('show'); cur = null; }, 180); }
  document.addEventListener('mouseover', function (e) {
    var el = e.target.closest && e.target.closest('.pick'); if (el && el.dataset.slug) show(el);
    var cb = e.target.closest && e.target.closest('.combo'); if (cb) showCombo(cb);
  });
  document.addEventListener('mouseout', function (e) {
    var el = e.target.closest && e.target.closest('.pick'); if (el && el.dataset.slug) hide();
    if (e.target.closest && e.target.closest('.combo')) hide();
  });
  document.addEventListener('focusin', function (e) { if (e.target.dataset && e.target.dataset.slug) show(e.target); else if (e.target.classList && e.target.classList.contains('combo')) showCombo(e.target); });
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
    js = HERO_JS.replace("__HERO__", json.dumps({k: hero.get(k) for k in ("photo", "mask", "roof", "zones")}).replace("</", "<\\/"))
    return HERO_CSS, html, js

# The floating back-to-top button: position and show/hide are shared, the look is each theme's `.to-top` rule.
# Filament columns of a colour start collapsed (only with JS: html.js is set by TOP_JS, without it everything shows).
ROWS_CSS = """
.rows-bar, .row-toggle { display: none; }
html.js .rows-bar { display: flex; gap: 6px; margin: 0 0 8px; }
.rows-bar button, .row-toggle { font: inherit; font-size: 0.72rem; color: inherit; background: transparent; border: 1px solid var(--rule); padding: 2px 8px; cursor: pointer; }
.rows-bar button:hover, .row-toggle:hover, .row-toggle:focus-visible { background: var(--rule); }
html.js .row-toggle { display: inline-flex; align-items: center; gap: 6px; margin-top: 8px; }
.row-toggle::after { content: "▾"; font-size: 0.8em; transition: transform .15s; }
article.row.open .row-toggle::after { transform: rotate(180deg); }
html.js article.row:not(.open) .rcols { display: none !important; }
html.js article.row:not(.open) .paint-col { margin-bottom: 0; }
"""
ROWS_JS = """
(function () {
  function set(row, open) {
    row.classList.toggle('open', open);
    var b = row.querySelector('.row-toggle'); if (b) b.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('.row-toggle');
    if (t) { var row = t.closest('article.row'); set(row, !row.classList.contains('open')); return; }
    var all = e.target.closest && e.target.closest('[data-rows]');
    if (all) document.querySelectorAll('article.row').forEach(function (r) { set(r, all.dataset.rows === 'open'); });
  });
  window.openRow = function (row) { set(row, true); };
})();
"""

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

def counter_html():
    """GoatCounter hit tag + footer visitor number. Empty without config.GOATCOUNTER.
    count.js itself skips localhost and file://, so previews don't count."""
    code = config.GOATCOUNTER
    if not code:
        return ""
    host = f"https://{code}.goatcounter.com"
    return (f'<script data-goatcounter="{host}/count" async src="//gc.zgo.at/count.js"></script>\n'
            "<script>(function(){var v=document.getElementById('vc');if(!v)return;"
            f"fetch('{host}/counter/TOTAL.json').then(function(r){{return r.json()}})"
            ".then(function(d){v.textContent='Visitor no. '+d.count;v.hidden=false}).catch(function(){});})();</script>")

def merge_fonts(*queries):
    """Google Fonts `family=...` queries joined, each family once"""
    fams = []
    for q in queries:
        for fam in re.findall(r"family=[^&\s]+", q):
            if fam not in fams:
                fams.append(fam)
    return "&".join(fams)


def head_offsets(d):
    """header-card offsets and colours saved by the layout editor (`?edit` on scripts/serve_preview.py)"""
    def part(f):
        fp = d / f
        return fp.read_text() if fp.is_file() else ""
    mobile = part("headcard-offsets-mobile.css")
    return part("headcard-offsets.css") + part("headcard-colors.css") + (f"@media (max-width: 520px) {{\n{mobile}}}\n" if mobile.strip() else "")


def load_theme(name):
    """dict of css, fonts query, header motif html and, for a theme with tile-style header (tokens.css), tokens,
    headcard css and tile decoration, read from themes/<name>/. Each car picks one in car.json."""
    d = config.THEMES / name
    if not (d / "theme.css").is_file():
        sys.exit(f"theme '{name}' not found: expected {d}/theme.css")
    def part(f):
        fp = d / f
        return fp.read_text().strip() if fp.is_file() else ""
    return {"css": part("theme.css"), "fonts": part("fonts.txt"), "motif": part("motif.html"), "tokens": part("tokens.css"),
            "headcard": part("headcard.css"), "deco": part("tile.html"), "tile": part("tile.css"), "tile_fonts": part("tile-fonts.txt"),
            "head_offsets": head_offsets(d)}

def region_css(regions, finish_keys=()):
    """Show only the active region's candidates and counts (body[data-region]); with finish toggles
    (`finish_keys`, one per state) also only the candidate lists of the active state (body[data-finish])."""
    out = ["[data-r] { display: none; }"]
    for r in regions:
        out.append(f'body[data-region="{r}"] div[data-r="{r}"]:not(.rcols) {{ display: block; }}')
        out.append(f'body[data-region="{r}"] span[data-r="{r}"] {{ display: inline; }}')
        if finish_keys:
            out += [f'body[data-region="{r}"][data-finish="{k}"] .rcols[data-r="{r}"][data-f~="{k}"] {{ display: contents; }}' for k in finish_keys]
        else:
            out.append(f'body[data-region="{r}"] .rcols[data-r="{r}"] {{ display: contents; }}')
    return "\n".join(out)

SPACING_CSS = """
/* vertical rhythm shared by every theme: paint rows and the candidates in them breathe */
.row { padding: 30px 0; row-gap: 22px; }
.col-label { margin-bottom: 12px; }
.no-match { margin-bottom: 12px; }
.filament.primary { margin-bottom: 14px; padding-bottom: 14px; border-bottom: 1px solid var(--rule-soft); }
.filament.alt { padding-top: 8px; padding-bottom: 8px; }
"""

REGION_SWITCH_CSS = """
.region-switch button { font: inherit; cursor: pointer; }
"""

# `?edit` on scripts/serve_preview.py loads the layout editor for the header card (the file does not exist on Pages)
EDITOR_LOADER = """<script>if (/[?&]edit\\b/.test(location.search)) { var s = document.createElement('script'); s.src = '/__editor.js'; document.head.appendChild(s); }</script>"""

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

# Finish toggles: body[data-finish] is the key of the pressed set ('-' = none, 'glitter+matt' ...), ?finish=glitter,matt in the URL.
FINISH_JS = """
<script>
(function () {
  var btns = [].slice.call(document.querySelectorAll('[data-finish-btn]')), order = btns.map(function (b) { return b.dataset.finishBtn; });
  function key() { var on = btns.filter(function (b) { return b.getAttribute('aria-pressed') === 'true'; }).map(function (b) { return b.dataset.finishBtn; }); return on.join('+') || '-'; }
  function apply(keep) {
    document.body.dataset.finish = key();
    if (keep) return;
    try { var u = new URL(location.href), on = key(); if (on === '-') u.searchParams.set('finish', ''); else u.searchParams.set('finish', on.replace(/\\+/g, ',')); history.replaceState(null, '', u); } catch (e) {}
  }
  btns.forEach(function (b) { b.onclick = function () { b.setAttribute('aria-pressed', b.getAttribute('aria-pressed') === 'true' ? 'false' : 'true'); apply(); }; });
  var want = null;
  try { want = new URL(location.href).searchParams.get('finish'); } catch (e) {}
  if (want !== null) {
    var set = want.split(',');
    btns.forEach(function (b) { b.setAttribute('aria-pressed', set.indexOf(b.dataset.finishBtn) >= 0 ? 'true' : 'false'); });
  }
  apply(true);
})();
</script>
"""

def _norm(n):
    return n.replace(" Poly", "").lower()

def load_combinations(car, hero):
    """Factory two-tone combinations that can be shown: the car has a preview with slots, every colour of the
    combination is a paint of the car (an entry with `unresolved` has a colour without chip and is kept in the file,
    not published) and the slots it names exist on the car (Doppler has no intermediate slot)."""
    path = config.car_dir(car) / "combinations.json"
    if not (hero and path.exists()):
        return {}
    ids = {z["id"] for z in hero.get("zones") or [] if z.get("label")}
    out = {}
    for year, v in json.loads(path.read_text(encoding="utf-8")).get("years", {}).items():
        ok = [c for c in v["combinations"] if "unresolved" not in c and {z for z in ("upper", "intermediate", "lower") if c.get(z)} <= ids]
        if ok:
            out[int(year)] = ok
    return out

def combos_html(year, combos, matches):
    """The 'Factory two-tones' strip under a year heading: one button per combination, upper colour over lower."""
    items = combos.get(year)
    if not items:
        return ""
    def find(name):
        c = [m for m in matches if _norm(m["name"]) == _norm(name)]
        c.sort(key=lambda m: abs(m["year"] - year))
        return c[0] if c else None
    btns = []
    for c in items:
        cols = {z: find(c[z]) for z in ("upper", "lower") if c.get(z)}
        if len(cols) < 2 or not all(cols.values()):
            continue
        attrs = " ".join(f'data-{z}="{esc(m["name"])}" data-{z}-year="{m["year"]}"' for z, m in cols.items())
        def tip(m):
            return m["name"] + ("" if m["year"] == year else f" ({m['year']} card)")
        sw = "".join(f'<i class="cb-sw" style="background:{cols[z]["hex"]}" title="{esc(tip(cols[z]))}"></i>' for z in ("upper", "lower"))
        btns.append(f'<button type="button" class="combo" {attrs} title="{esc(cols["upper"]["name"])} over {esc(cols["lower"]["name"])}">'
                    f'<span class="cb-code">{esc(c["code"])}</span>{sw}</button>')
    if not btns:
        return ""
    return (f'<div class="combos" data-year="{year}"><span class="combos-l">Factory two-tones</span>' + "".join(btns) +
            '<span class="combos-hint">click the active one again to show all colours</span></div>')

def _chip_key(m):
    return (m["name"], m.get("year"), m.get("car_code", ""))


def render(car, matches_by_region, fil_thumbs, all_filaments, meta, hero=None, variants=None):
    """The whole self-contained page as a string. `matches_by_region` is {region: [match, ...]} for the car's default
    finishes; `variants` is {finish key: matches_by_region} for every state of the finish toggles (including the default)."""
    default_key = compute_matches.finish_key(compute_matches.allowed_finishes(meta))
    variants = variants or {default_key: matches_by_region}
    finish_ui = len(variants) > 1
    labels  = region_labels()
    regions = [r for r in labels if r in matches_by_region]
    matches = matches_by_region[regions[0]]          # same colours in every region
    DISPLAY    = meta.get("display", car.title())
    SCRIPT_TAG = meta.get("script_tagline", "")
    BADGE_TOP  = meta.get("badge_label", DISPLAY.upper())
    theme_name = meta.get("theme", "default")
    theme = load_theme(theme_name)
    fonts_q, motif_html = theme["fonts"], theme["motif"]
    use_card = bool(theme["tokens"])
    if use_card:
        fonts_q = merge_fonts(fonts_q, theme["tile_fonts"])
    theme_css = (TILE_BASE_CSS + theme["tokens"] + theme["css"] + theme["tile"] + theme["headcard"] + theme["head_offsets"]) if use_card else theme["css"]

    # One chip = name + year + code: two paints can share a name (Bamboo's "White" 031 and 033).
    by_chip = {k: {r: {_chip_key(m): m for m in mbr[r]} for r in regions} for k, mbr in variants.items()}
    by_year = {}
    for m in matches:
        if m.get("year") is None:
            print(f"! {m['name']}: no year, left out of the page")
            continue
        by_year.setdefault(m["year"], []).append(m)
    total_count = sum(len(v) for v in by_year.values())

    USED_THUMBS.clear()
    combos = load_combinations(car, hero)
    rows = ['<div class="rows-bar"><button type="button" data-rows="open">Show all filaments</button>'
            '<button type="button" data-rows="close">Hide all</button></div>']
    for year in sorted(by_year.keys(), reverse=True):
        rows.append(f"""
      <h2 class="year-head" id="y{year}">
        <span class="year-badge">
          <span class="year-badge-top">{BADGE_TOP}</span>
          <span class="year-badge-num">{year}</span>
        </span>
        <span class="year-tagline">Model Year</span>
      </h2>""")
        rows.append(combos_html(year, combos, matches))
        for m in by_year[year]:
            cols = ""
            for r in regions:
                # one candidate block per distinct result; a block lists every finish state it is right for
                blocks = {}
                for k in variants:
                    cand = by_chip[k][r][_chip_key(m)]
                    blocks.setdefault(f"""
          <div class="col pla-col">{filament_column(cand['pla'], 'PLA', fil_thumbs)}</div>
          <div class="col petg-col">{filament_column(cand['petg'], 'PETG', fil_thumbs)}</div>
          <div class="col asa-col">{filament_column(cand.get('asa', []), 'ASA', fil_thumbs)}</div>""", []).append(k)
                for inner, keys in blocks.items():
                    f_attr = f' data-f="{" ".join(keys)}"' if finish_ui else ""
                    cols += f'\n          <div class="rcols" data-r="{r}"{f_attr}>{inner}\n          </div>'
            rows.append(f"""
        <article class="row" id="c{m['year']}-{slugify(m['name'])}" data-paint="{esc(m['name'])}" data-year="{m['year']}">
          <div class="col paint-col">{paint_block(m)}<button type="button" class="row-toggle" aria-expanded="false" title="Show the filaments for this colour"><span>Filaments</span></button></div>{cols}
        </article>
        """)

    counts, card_counts = "", ""
    for r in regions:
        fr = [f for f in all_filaments if r in (f.get("regions") or []) and f.get("rgb")]
        pla_n  = sum(1 for f in fr if f["material"] in config.PLA_MATERIALS)
        petg_n = sum(1 for f in fr if f["material"] in config.PETG_MATERIALS)
        asa_n  = sum(1 for f in fr if f["material"] in config.ASA_MATERIALS)
        shops  = {f.get("shop", "?") for f in fr}
        counts += (f'<div data-r="{r}"><strong>{pla_n}</strong><span>PLA candidates</span></div>'
                   f'<div data-r="{r}"><strong>{petg_n}</strong><span>PETG candidates</span></div>'
                   f'<div data-r="{r}"><strong>{asa_n}</strong><span>ASA candidates</span></div>'
                   f'<div data-r="{r}"><strong>{len(shops)}</strong><span>e-shops</span></div>')
        card_counts += (f'<span data-r="{r}">{pla_n} PLA · {petg_n} PETG · {asa_n} ASA · {len(shops)} e-shops</span>')
    switch = ""
    if len(regions) > 1:
        switch = ('<div class="year-nav region-switch"><span class="nav-label">Shops in:</span>'
                  + "".join(f'<button type="button" data-region-btn="{r}" aria-pressed="{"true" if r == regions[0] else "false"}">{esc(labels[r])}</button>'
                            for r in regions)
                  + '</div>')

    if finish_ui:
        on = set(default_key.split("+"))
        switch += ('<div class="year-nav region-switch finish-switch"><span class="nav-label">Finishes:</span>'
                   + "".join(f'<button type="button" data-finish-btn="{n}" aria-pressed="{"true" if n in on else "false"}" '
                             f'title="Show {n} filaments">{n.title()}</button>' for n in finish_names())
                   + '</div>')

    _years = sorted(by_year.keys())
    _year_range = f"{_years[0]}-{_years[-1]}" if _years else ""
    _year_links = sorted(by_year.keys(), reverse=True)
    hero_css, hero_html, hero_js = hero_parts(hero)
    year_nav = ('<nav class="year-nav"><span class="nav-label">Jump to year:</span>'
                + "".join(f'<a href="#y{y}">{y}</a>' for y in _year_links) + '</nav>')
    if use_card:
        header_html = head_card_html(theme_name, DISPLAY, SCRIPT_TAG,
                                     f'{_year_range} · {total_count} paint colours<br>{card_counts}',
                                     theme["deco"], switch + year_nav)
    else:
        header_html = f"""<header class="page-head">
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
  {year_nav}
</header>"""
    tip_js = TIP_JS.replace("__THUMBS__", json.dumps({k: fil_thumbs[k] for k in sorted(USED_THUMBS)}).replace("</", "<\\/"))
    return f"""<!doctype html>
<html lang="en" class="theme-{esc(theme_name)}">
<head>
<meta charset="utf-8">
<title>{esc(DISPLAY)} · {_year_range} color card</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<style>
{theme_css}
{TOP_CSS}
{ROWS_CSS}
{REGION_SWITCH_CSS}
{region_css(regions, list(variants) if finish_ui else ())}
{PICK_CSS}
{hero_css}
{SPACING_CSS}
{TIP_CSS}
</style>

<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{esc(fonts_q)}&display=swap">
</head>
<body id="top" data-region="{regions[0]}"{f' data-finish="{default_key}"' if finish_ui else ""} data-car="{esc(car)}">

{header_html if use_card else ""}

<div class="paper">

{"" if use_card else header_html}



<main>
  {''.join(rows)}
</main>

<footer class="card-footer">
  <div class="legend">
    <span class="legend-head">ΔE2000 scale</span>
    <span class="lblock"><span class="pill exc">&lt; 2</span> excellent</span>
    <span class="lblock"><span class="pill vg">2-4</span> very good</span>
    <span class="lblock"><span class="pill ok">4-7</span> good</span>
    <span class="lblock"><span class="pill weak">7-12</span> noticeable shift</span>
    <span class="lblock"><span class="pill bad">&gt; 12</span> large difference</span>
  </div>
  <div class="brand">{esc(DISPLAY)} factory colors · 3D-print filament matches</div>
  <div class="sub">Generated by car-paint-filaments · {_year_range} color cards · {date.today().year}</div>
  {'<div class="visit-count" id="vc" hidden></div>' if config.GOATCOUNTER else ''}
</footer>

</div>
<a class="to-top" href="#top" aria-label="Back to top"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 3.5 12.5H9V21h6v-8.5h5.5z"/></svg><span>Back to top</span></a>
<script>{TOP_JS}</script>
<script>{ROWS_JS}</script>
{hero_html}
{hero_js}
{tip_js}
{REGION_JS if len(regions) > 1 else ""}
{FINISH_JS if finish_ui else ""}
{EDITOR_LOADER if use_card else ""}
{counter_html()}
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
    meta = config.car_meta(args.car)
    # every state of the finish toggles gets its own candidate lists (a hidden finish must not leave a row short)
    colors = {r: [dict(m) for m in ms] for r, ms in matches.items()}
    pool = [f for f in all_filaments if f.get("rgb")]
    variants = {compute_matches.finish_key(a): {r: compute_matches.match_colors(colors[r], pool, r, a) for r in colors}
                for a in compute_matches.all_finish_sets()}
    page = render(args.car, matches, thumbs["filaments"], all_filaments, meta, hero, variants)

    out = config.car_output(args.car) / f"{args.car}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(out, page)
    print(f"HTML: {out} ({out.stat().st_size/1024:.1f} KB)")

if __name__ == "__main__":
    main()
