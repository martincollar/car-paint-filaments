"""Print a car's chip review as a static, self-contained colour-review PDF.

Same information as review_chips.py's live page, but a non-interactive report
in the "Bamboo: colour review" format: a summary header, then one detail card
per colour with the chip scan, measured swatch, your pick (if overridden), and
the real-car photo with confidence and notes. Colours are grouped by family
(whites/greys, beige/sand, yellow, orange, red, green, blue) rather than the
source chart's "standard / special" split, so related colours (e.g. all three
yellows) sit together.

    python src/colour_review_report.py --car unimog406 --pdf OUT.pdf
"""
from __future__ import annotations
import argparse, html, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import config
from review_chips import load  # reuse the same data loading

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Family-grouped order (the source chart lists "standard" then "special" colours,
# which splits related colours apart, e.g. chrome yellow ends up far from curry/
# amber yellow). This groups by what the colour actually looks like.
FAMILY_ORDER = [
    "db9136", "db7701", "db7187",            # grey-white, pebble grey, lorry grey
    "db1448", "db1474",                      # brown beige, desert sand
    "db1600", "db1624", "ral1004",           # curry yellow, amber yellow, chrome yellow
    "db2550", "db2603",                      # yellow orange, brown orange
    "db2553", "db3534",                      # red orange, fire red
    "db6277", "ral6014", "db6821", "db6294", "db6840",  # the five greens
    "db5361",                                # gentian blue
]

CSS = """
:root{--line:#d9d6cf;--muted:#6b6b66;--ink:#1c1c1a}
*{box-sizing:border-box}
body{font:13px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:var(--ink);background:#fff}
.bar{display:flex;align-items:center;gap:16px;background:#1c2430;color:#fff;padding:14px 22px}
.bar h1{font-size:17px;margin:0;font-weight:600}
.bar .stats{font-size:12px;color:#c6ccd6}
.page{padding:18px 22px 30px}
h2{font-size:15px;margin:22px 0 10px}
.sw{width:64px;height:28px;border-radius:4px;border:1px solid var(--line);display:inline-block}
.hexlbl{font-size:10px;color:var(--muted);font-family:ui-monospace,Menlo,monospace;display:block;margin-top:2px}
.tag{display:inline-block;font-size:9.5px;border-radius:3px;padding:0 5px;margin-left:4px}
.tag.good{background:#e3f2e3;color:#1b5e20}
.tag.tentative{background:#fde9c8;color:#8a5a00}
.tag.none{background:#f3e3e3;color:#8a1a1a}
.card{border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:14px;break-inside:avoid}
.card h3{margin:0 0 2px;font-size:14px}
.card .code{font-size:11px;color:var(--muted);margin-bottom:8px}
.row{display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap}
.swatches{display:flex;gap:8px}
.swatches .box{text-align:center;font-size:10px;color:var(--muted)}
.swatches .box .sw{width:72px;height:50px}
.chip{width:110px;height:auto;border:1px solid var(--line);border-radius:4px}
.real{width:220px;max-height:150px;object-fit:cover;border:1px solid var(--line);border-radius:4px}
.real-missing{width:220px;min-height:90px;border:1px dashed var(--line);border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--muted);text-align:center;padding:8px}
.note{flex:1;min-width:220px;font-size:11.5px;color:#444}
.note .credit{font-size:10px;color:#9a9890;margin-top:4px}
@page{size:A3 landscape;margin:14mm}
"""


def detail_card(r) -> str:
    code = html.escape(r["code"]) + (f" · {html.escape(r['ral'])}" if r.get("ral") else "")
    pick = r["override"]
    swatches = f"""<div class="swatches">
 <div class="box"><span class="sw" style="background:{r['measured'].upper()}"></span>measured<br>{r['measured'].upper()}</div>
 {f'<div class="box"><span class="sw" style="background:{pick}"></span>your pick<br>{pick}</div>' if pick else ''}
</div>"""
    if r["real_uri"]:
        tag = f'<span class="tag {r["real_confidence"]}">{html.escape(r["real_confidence"])} match</span>'
        real = f'<img class="real" src="{r["real_uri"]}">'
    else:
        tag = '<span class="tag none">no match</span>'
        real = '<div class="real-missing">No credible real-car photo found.</div>'
    note = html.escape(r["real_note"]) if r["real_note"] else ""
    credit = html.escape(r["real_credit"]) if r["real_credit"] else ""
    return f"""<div class="card">
 <h3>{html.escape(r['name'])} {tag}</h3>
 <div class="code">{code}</div>
 <div class="row">
   <img class="chip" src="{r['chip_uri']}">
   {swatches}
   {real}
   <div class="note">{note}{f'<div class="credit">{credit}</div>' if credit else ''}</div>
 </div>
</div>"""


def build(car: str) -> str:
    rows, _ = load(car)
    by_key = {r["key"]: r for r in rows}
    ordered = [by_key[k] for k in FAMILY_ORDER if k in by_key]
    missing = [r for r in rows if r["key"] not in FAMILY_ORDER]
    ordered += missing  # safety net, shouldn't trigger

    n_good = sum(1 for r in ordered if r["real_confidence"] == "good")
    n_tent = sum(1 for r in ordered if r["real_confidence"] == "tentative")
    n_none = sum(1 for r in ordered if not r["real_uri"])
    n_picked = sum(1 for r in ordered if r["override"])
    disp = config.car_meta(car).get("display") or "Mercedes-Benz Unimog 406/416 (1963–70)"

    details = "\n".join(detail_card(r) for r in ordered)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(disp)}: colour review</title><style>{CSS}</style></head><body>
<div class="bar"><h1>{html.escape(disp)}: colour review</h1>
<div class="stats">{len(ordered)} colours · {n_good} good match · {n_tent} tentative · {n_none} no real photo · {n_picked} with a hand override</div></div>
<div class="page">
<h2>Colours with photos</h2>
{details}
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    ap.add_argument("--out", help="write the static HTML here (default cars/<car>/data/colour_review_report.html)")
    ap.add_argument("--pdf", help="also print to this PDF with headless Chrome")
    args = ap.parse_args()

    page = build(args.car)
    out_html = Path(args.out) if args.out else config.car_data(args.car) / "colour_review_report.html"
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(page, encoding="utf-8")
    print("html →", out_html)

    if args.pdf:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                         f"--print-to-pdf={args.pdf}", out_html.resolve().as_uri()], check=True,
                        capture_output=True)
        print("pdf →", args.pdf)


if __name__ == "__main__":
    main()
