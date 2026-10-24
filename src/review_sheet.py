"""Visual check of filament measurements: product photo next to the measured colour.

Writes a self-contained HTML contact sheet (base64 thumbnails) so a human can
see at a glance where `filament_rgb()` measured the box, the spool or the
background instead of the filament.

A card is flagged when
  - box:     the photo is mostly kraft cardboard (`color_tools.kraft_share()` > 0.12)
             AND the measured colour itself looks like cardboard AND the name isn't
             a beige/brown family colour (those legitimately look like kraft), or
  - cluster: 3+ differently named colours of one brand in one shop measure within
             ΔE 2 of it (the photos show packaging, not the colour).
Manual overrides (`confidence: manual_override`) are never flagged.

Records whose colour moved by ΔE >= 3 in the last measure_filaments.py run carry
`previous_hex`; they get their own "Changed" section with old and new swatches.

Usage:
    python review_sheet.py                         # flagged first, then a sample of OK ones
    python review_sheet.py --shop Smart3D --all    # every Smart3D card
    python review_sheet.py --out /tmp/sheet.html --no-open
"""
import argparse, collections, html, json, random, sys, webbrowser
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
import config
from color_tools import (_load, delta_e_2000, delta_e_2000_many, hex_to_rgb, kraft_share,
                         kraft_like_rgb, kraft_like_name, rgb_to_lab)
from prepare_thumbnails import to_b64_jpg

KRAFT_FLAG = 0.12

def kraft_like_hex(hx):
    return kraft_like_rgb(hex_to_rgb(hx))

def cluster_flags(records):
    groups = collections.defaultdict(list)
    for r in records:
        if r.get("confidence") == "measured_dominant_hue":
            groups[(r["shop"], r["brand"])].append(r)
    flagged = set()
    for members in groups.values():
        lab = rgb_to_lab([g["rgb"] for g in members])
        close = delta_e_2000_many(lab[:, None, :], lab[None, :, :]) < 2.0     # n × n, diagonal True
        for i, r in enumerate(members):
            near = {members[j]["color_name"] for j in np.flatnonzero(close[i])}
            if len(near | {r["color_name"]}) >= 3:
                flagged.add(r["slug"])
    return flagged

def card(r, why, show_previous=False):
    src = config.FILAMENTS_SOURCES / r["local_image"]
    thumb = to_b64_jpg(Image.fromarray(_load(src)), max_dim=160, quality=74) if src.exists() else ""
    e = html.escape
    tags = "".join(f'<span class="tag">{e(w)}</span>' for w in why)
    if show_previous and r.get("previous_hex"):
        swatches = (f'<div class="sw old" style="background:{r["previous_hex"]}" title="before {r["previous_hex"]}"></div>'
                    f'<div class="sw" style="background:{r["hex"]}" title="now {r["hex"]}"></div>')
        pair_cls = "pair three"
    else:
        swatches, pair_cls = f'<div class="sw" style="background:{r["hex"]}"></div>', "pair"
    return f"""<figure class="card{' flag' if why else ''}">
  <div class="{pair_cls}"><img src="{thumb}" alt="">{swatches}</div>
  <figcaption><b>{e(r['brand'])}</b> {e(r['material'])} · {e(r['color_name'])}<br>
  <span class="meta">{e(r['shop'])} · {(r['previous_hex'] + ' → ') if show_previous and r.get('previous_hex') else ''}{r['hex']} · box {r['_kraft']:.2f}</span> {tags}<br>
  <a href="{e(r['url'])}" target="_blank" rel="noopener">shop ↗</a></figcaption></figure>"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shop", help="only this shop (display name, e.g. Smart3D)")
    ap.add_argument("--all", action="store_true", help="every card, not flagged + sample")
    ap.add_argument("--ok-sample", type=int, default=60)
    ap.add_argument("--out", default=str(config.FILAMENTS_CACHE / "review_sheet.html"))
    ap.add_argument("--no-open", action="store_true", help="don't open the sheet in the browser")
    args = ap.parse_args()

    recs = [r for r in json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8"))
            if r.get("rgb") and r.get("local_image")
            and (not args.shop or r["shop"] == args.shop)]
    print(f"{len(recs)} filaments: looking for same-colour clusters…", flush=True)
    clusters = cluster_flags(recs)
    flagged, ok = [], []
    for i, r in enumerate(recs, 1):
        if i % 200 == 0 or i == len(recs):
            print(f"  checked {i}/{len(recs)} photos", flush=True)
        src = config.FILAMENTS_SOURCES / r["local_image"]
        r["_kraft"] = kraft_share(src) if src.exists() else 0.0
        why = []
        if r.get("confidence") != "manual_override":
            if (r["_kraft"] > KRAFT_FLAG and kraft_like_hex(r["hex"])
                    and not kraft_like_name(r["color_name"])):
                why.append("box")
            if r["slug"] in clusters:   why.append("cluster")
        (flagged if why else ok).append((r, why))
    changed = sorted((x for x in flagged + ok if x[0].get("previous_hex")),
                     key=lambda x: -delta_e_2000(hex_to_rgb(x[0]["previous_hex"]), x[0]["rgb"]))
    if not args.all:
        random.seed(0)
        ok = random.sample(ok, min(args.ok_sample, len(ok)))
    key = lambda x: (x[0]["shop"], x[0]["brand"], x[0]["color_name"])
    flagged.sort(key=key); ok.sort(key=key)

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Measurement review</title>
<style>
:root {{ --bg:#f6f1e7; --ink:#2b2620; --muted:#7a7064; --line:#d9cfbf; --bad:#b3261e; }}
body {{ background:var(--bg); color:var(--ink); font:14px/1.4 system-ui,sans-serif; margin:0; padding:16px; }}
h1 {{ font-size:20px; margin:0 0 4px; }} h2 {{ font-size:16px; margin:28px 0 8px; }}
p.lead {{ color:var(--muted); margin:0 0 12px; max-width:70ch; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:10px; }}
.card {{ margin:0; background:#fff; border:1px solid var(--line); border-radius:8px; padding:8px; }}
.card.flag {{ border-color:var(--bad); }}
.pair {{ display:grid; grid-template-columns:1fr 1fr; gap:6px; height:120px; }}
.pair.three {{ grid-template-columns:2fr 1fr 1fr; }}
.pair img {{ width:100%; height:120px; object-fit:contain; background:#fff; }}
.sw.old {{ opacity:.9; outline:2px dashed rgba(0,0,0,.25); outline-offset:-4px; }}
.sw {{ border-radius:6px; border:1px solid rgba(0,0,0,.12); }}
figcaption {{ margin-top:6px; font-size:12.5px; }}
.meta {{ color:var(--muted); font-variant-numeric:tabular-nums; }}
.tag {{ display:inline-block; background:var(--bad); color:#fff; border-radius:3px; padding:0 5px; font-size:11px; margin-left:3px; }}
a {{ color:var(--ink); }}
</style></head><body>
<h1>Measurement review</h1>
<p class="lead">Left: shop photo. Right: the colour <code>filament_rgb()</code> measured from it.
If the right square doesn't look like the filament, the measurement is wrong.
<b>box</b> = photo is mostly kraft cardboard (share &gt; {KRAFT_FLAG}); <b>cluster</b> = 3+ colours of one brand measure the same.
{len(recs)} filaments{(' in ' + html.escape(args.shop)) if args.shop else ''}, {len(flagged)} flagged.</p>
<h2>Changed by the last measurement ({len(changed)})</h2>
<p class="lead">Photo · colour before · colour now, biggest change first. Check that "now" matches the photo better.</p>
<div class="grid">{''.join(card(r, w, show_previous=True) for r, w in changed)}</div>
<h2>Flagged ({len(flagged)})</h2><div class="grid">{''.join(card(r, w) for r, w in flagged)}</div>
<h2>{'All' if args.all else 'Random sample of'} unflagged ({len(ok)})</h2><div class="grid">{''.join(card(r, w) for r, w in ok)}</div>
</body></html>"""
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"→ {out}  ({len(flagged)} flagged, {len(ok)} ok shown, {out.stat().st_size // 1024} KB)")
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())

if __name__ == "__main__":
    main()
