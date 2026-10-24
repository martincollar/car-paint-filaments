"""Build HTML page — all car colors × filament matches, retro styling.

Usage:
    python build_html.py [--car <name>]
"""
import argparse, json, re, sys, html as html_mod
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import config

_ap = argparse.ArgumentParser()
_ap.add_argument("--car", default=config.DEFAULT_CAR)
_ap.add_argument("--library", default="cz", choices=["cz", "intl"])
_args = _ap.parse_args()

CAR = _args.car
LIBRARY = _args.library
LIBRARY_LABEL = {"cz": "Czech e-shops", "intl": "FilamentColors.xyz library"}[LIBRARY]
CAR_META = config.car_meta(CAR)
DISPLAY       = CAR_META.get("display", CAR.title())
SCRIPT_TAG    = CAR_META.get("script_tagline", "")
BADGE_TOP     = CAR_META.get("badge_label", DISPLAY.upper())

CAR_DATA = config.car_data(CAR)
OUT_NAME = f"{CAR}.html" if LIBRARY == "cz" else f"{CAR}-{LIBRARY}.html"
OUT      = config.car_output(CAR) / OUT_NAME

matches  = json.loads((CAR_DATA / f"matches_{LIBRARY}.json").read_text(encoding="utf-8"))
thumbs   = json.loads((CAR_DATA / f"thumbnails_{LIBRARY}.json").read_text(encoding="utf-8"))
all_filaments = [f for f in json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8"))
                 if f.get("library", "cz") == LIBRARY]
car_thumbs    = thumbs.get("car") or thumbs.get("hudson", {})
fil_thumbs    = thumbs["filaments"]

def de_class(dE):
    if dE < 2: return "exc"
    if dE < 4: return "vg"
    if dE < 7: return "ok"
    if dE < 12: return "weak"
    return "bad"

by_year = {}
for m in matches:
    by_year.setdefault(m["year"], []).append(m)

total_count = sum(len(v) for v in by_year.values())

def esc(s): return html_mod.escape(str(s))

def hudson_block(h):
    poly = ' <span class="chip">metallic</span>' if h.get("poly") else ""
    return f"""
      <div class="paint">
        <div class="swatch big" style="background:{h['hex']}"></div>
        <div class="meta">
          <div class="name">{esc(h['name'])}{poly}</div>
          <div class="sub">
            <span class="year">{h['year']}</span>
            · {esc(h['hudson_code'])}
            · ref. {esc(h['ditzler'])}
          </div>
          <div class="hex">{h['hex']} <span class="rgb">RGB {h['rgb'][0]},{h['rgb'][1]},{h['rgb'][2]}</span></div>
        </div>
      </div>
    """

def shop_tag(shop):
    sl = (shop or "?").lower()
    return f'<span class="shop-tag shop-{sl}">{esc(shop or "?")}</span>'

# Shop links in the published page must not carry anyone's affiliate or tracking
# codes (FilamentColors.xyz buy links do). Shortener links hide the code in the
# redirect, so they fall back to the swatch page on FilamentColors.xyz.
SHORTENERS = {"amzn.to", "collabs.shop", "bit.ly", "geni.us", "shrsl.com", "tinyurl.com"}
TRACKING_PARAMS = re.compile(r"^(utm_.*|aff.*|a_aid|a_bid|ref|ref_|tag|ascsubtag|linkcode|linkid|camp|creative|creativeasin|ie"
                             r"|sca_ref|srsltid|gclid|fbclid|mc_.*|_pos|_psq|_ss|_v|_sid|variant_tracking)$", re.I)

def clean_url(c):
    url = c.get("url") or ""
    parts = urlsplit(url)
    if parts.hostname in SHORTENERS:
        return f"https://filamentcolors.xyz/swatch/{c['slug']}/"
    path = re.sub(r"/ref=[^/]*", "", parts.path)          # amazon /ref=… path segments
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not TRACKING_PARAMS.match(k)])
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))

def filament_row(c, is_primary=False):
    cls = de_class(c["delta_e"])
    tsrc = fil_thumbs.get(c["slug"], "")
    sw_cls = "mini" if is_primary else "tiny"
    thumb = f'<img class="fil-thumb" src="{tsrc}" alt="">' if tsrc and is_primary else ""
    name = f"<strong>{esc(c['brand'])}</strong> {esc(c['material'])} <span class=\"color\">{esc(c['color_name'])}</span>"
    if is_primary:
        return f"""
      <div class="filament primary">
        <div class="swatch {sw_cls}" style="background:{c['hex']}"></div>
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
        <span class="swatch {sw_cls}" style="background:{c['hex']}"></span>
        <span class="fname-inline">{name}</span>
        <span class="hex">{c['hex']}</span>
        <span class="de {cls}">ΔE {c['delta_e']:.1f}</span>
        {shop_tag(c.get('shop'))}
        <a class="shop-arrow" href="{esc(clean_url(c))}" target="_blank" rel="noopener">↗</a>
      </div>
    """

def filament_column(cands, kind):
    if not cands:
        return f'<div class="col-label">{kind}</div><div class="filament empty">no {kind} candidate</div>'
    out = [f'<div class="col-label">{kind}</div>']
    primary = cands[0]
    out.append(filament_row(primary, is_primary=True))
    # Alt kandidáti: jen ti, co mají "dobrou" shodu (< 10) nebo jsou blízko primary
    threshold = max(10.0, primary["delta_e"] + 2.0)
    alts = [c for c in cands[1:5] if c["delta_e"] < threshold]
    for c in alts:
        out.append(filament_row(c, is_primary=False))
    return "".join(out)

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
          <div class="col paint-col">{hudson_block(m)}</div>
          <div class="col pla-col">{filament_column(m['pla'], 'PLA')}</div>
          <div class="col petg-col">{filament_column(m['petg'], 'PETG')}</div>
        </article>
        """)

pla_n  = sum(1 for f in all_filaments if f["material"] in ("PLA","PLA+") and f.get("rgb"))
petg_n = sum(1 for f in all_filaments if f["material"] == "PETG" and f.get("rgb"))
shops  = sorted({f.get("shop","?") for f in all_filaments if f.get("rgb")})

# SVG starburst — mid-century atomic motif
STARBURST = '''<svg class="starburst" viewBox="-50 -50 100 100" aria-hidden="true">
  <g fill="currentColor">
    <polygon points="0,-46 3,-10 46,0 3,10 0,46 -3,10 -46,0 -3,-10"/>
    <polygon points="32,-32 7,-7 32,32 -7,7 -32,32 -7,-7 -32,-32 7,7" opacity="0.7"/>
  </g>
  <circle cx="0" cy="0" r="4" fill="currentColor"/>
</svg>'''

_years = sorted(by_year.keys())
_year_range = f"{_years[0]}-{_years[-1]}" if _years else ""
_year_links = sorted(by_year.keys(), reverse=True)
_title_suffix = " color card" if LIBRARY == "cz" else " · intl library"
html_doc = f"""<title>{esc(DISPLAY)} · {_year_range}{_title_suffix}</title>
<meta charset="utf-8">
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
</style>

<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Alfa+Slab+One&family=Yesteryear&family=Pacifico&family=Space+Mono:wght@400;700&family=Fraunces:ital,wght@0,400;0,500;0,600;1,400&display=swap">

<div class="paper">

<header class="page-head">
  {STARBURST}
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
  <div class="sub">Generated by car-paint-filaments · {_year_range} color cards · 2026</div>
</footer>

</div>
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html_doc)

print(f"HTML: {OUT} ({OUT.stat().st_size/1024:.1f} KB)")
