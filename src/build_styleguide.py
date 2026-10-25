"""Render a car theme's design language as one self-contained page: tokens, fonts, buttons, header card, table row.

Reads themes/<name>/{tokens.css,theme.css,tile.css,headcard.css,tile.html}; the sample elements are built with
the same functions as the real pages, so the guide cannot drift from them.

Usage:
    python build_styleguide.py --theme doppler     # writes themes/doppler/styleguide.html
"""
import argparse, html, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import config
from build_html import load_theme, merge_fonts, paint_block, filament_row
from tile_parts import head_card_html, TILE_BASE_CSS

SAMPLE_PAINT = {"name": "Gulf Green", "year": 1952, "car_code": "Q-115", "paint_ref": "41206", "hex": "#3A5F4B", "rgb": [58, 95, 75]}
SAMPLE_FIL = {"slug": "x", "brand": "Brand", "material": "PLA", "color_name": "Forest", "hex": "#3B6A4D", "delta_e": 2.4,
              "shop": "Smart3D", "url": "https://shop.example/p"}
GUIDE_CSS = """
.sg { max-width: 1100px; margin: 0 auto; padding: 24px 16px 60px; }
.sg h2 { margin: 36px 0 12px; font: 700 1.1rem var(--dl-font-ui); letter-spacing: .1em; text-transform: uppercase; color: var(--dl-ink); }
.sg-tokens { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; }
.sg-token { display: flex; gap: 10px; align-items: center; font: .8rem monospace; color: #222; }
.sg-chip { width: 44px; height: 44px; flex: none; border: 1px solid #0003; display: grid; place-items: center; font-size: .6rem; overflow: hidden; background: var(--v); }
.sg-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
"""


def tokens_of(theme):
    """{--dl-name: value} from tokens.css, in file order"""
    css = load_theme(theme)["tokens"]
    return dict(re.findall(r"(--dl-[a-z0-9-]+):\s*([^;]+);", css))


def build(theme):
    t = load_theme(theme)
    toks = tokens_of(theme)
    swatches = "".join(
        f'<div class="sg-token"><span class="sg-chip" style="--v: var({n})">{"Aa" if "font" in n else ""}</span>'
        f'<span><b>{n}</b><br>{html.escape(v)}</span></div>' for n, v in toks.items())
    fonts = "".join(f'<p style="font:700 1.6rem var({n})">{n}: Gulf Green 1952 — Fins, chrome &amp; flakes</p>'
                    for n in toks if "font" in n)
    buttons = ('<nav class="year-nav"><a href="#">1957</a><a href="#">1956</a></nav>'
               '<div class="year-nav region-switch"><button type="button" aria-pressed="true">EU / CZ</button>'
               '<button type="button" aria-pressed="false">INT</button></div>'
               '<a class="to-top" href="#" style="position:static"><svg viewBox="0 0 24 24"><path d="M12 3 3.5 12.5H9V21h6v-8.5h5.5z"/></svg></a>')
    card = head_card_html(theme, "Sample Name", "Tagline goes here", "1951-1957 · 65 paint colours", t["deco"],
                          '<nav class="year-nav"><span class="nav-label">Jump to year:</span><a href="#">1957</a></nav>')
    row = (f'<article class="row"><div class="col paint-col">{paint_block(SAMPLE_PAINT)}</div>'
           f'<div class="col pla-col"><div class="col-label">PLA</div>{filament_row(SAMPLE_FIL, {}, True)}</div></article>')
    css = TILE_BASE_CSS + t["tokens"] + t["css"] + t["tile"] + t["headcard"] + GUIDE_CSS
    fonts_q = merge_fonts(t["fonts"], t["tile_fonts"])
    return f"""<!doctype html>
<html lang="en" class="theme-{theme}"><head><meta charset="utf-8"><title>{theme} design language</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>{css}</style>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{fonts_q}&display=swap"></head>
<body><div class="sg"><h1>{theme}: design language</h1>
<h2>Tokens</h2><div class="sg-tokens">{swatches}</div>
<h2>Fonts</h2>{fonts}
<h2>Buttons</h2><div class="sg-row">{buttons}</div>
<h2>Header card</h2>{card}
<h2>Table row</h2><div class="paper">{row}</div>
</div></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", required=True)
    a = ap.parse_args()
    out = config.THEMES / a.theme / "styleguide.html"
    out.write_text(build(a.theme))
    print("wrote", out)
