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
    python review_sheet.py --brand lume --serve    # click wrong cards + reason, saved to filaments/.cache/review_marks_<brand>.json
"""
import argparse, collections, html, json, random, re, sys, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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

def card(r, why, show_previous=False, interactive=False):
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
    extra = ""
    if interactive:
        ov = f' · measured {r["measured_hex"]}' if r.get("measured_hex") else ""
        extra = (f'<br><span class="meta">{e(r["title"])}{ov}</span>'
                 f'<input class="reason" type="text" placeholder="reason (what it should be)" autocomplete="off">')
    return f"""<figure class="card{' flag' if why else ''}" data-slug="{e(r['slug'])}">
  <div class="{pair_cls}"><img src="{thumb}" alt="">{swatches}</div>
  <figcaption><b>{e(r['brand'])}</b> {e(r['material'])} · {e(r['color_name'])}<br>
  <span class="meta">{e(r['shop'])} · {(r['previous_hex'] + ' → ') if show_previous and r.get('previous_hex') else ''}{r['hex']} · box {r['_kraft']:.2f}</span> {tags}<br>
  <a href="{e(r['url'])}" target="_blank" rel="noopener">shop ↗</a>{extra}</figcaption></figure>"""

INTERACTIVE_CSS = """
.bar { position:sticky; top:0; z-index:5; background:var(--ink); color:#fff; margin:-16px -16px 14px; padding:8px 16px; display:flex; gap:14px; align-items:center; }
.bar button, .bar label { font:inherit; }
.bar button { background:#fff; border:0; border-radius:4px; padding:3px 10px; cursor:pointer; }
.bar #status { margin-left:auto; opacity:.7; font-size:12px; }
.card[data-slug] { cursor:pointer; position:relative; }
.card.wrong { border:2px solid var(--bad); background:#fdeceb; padding:7px; }
.card.wrong::after { content:"✗ wrong"; position:absolute; top:6px; right:8px; background:var(--bad); color:#fff; border-radius:3px; padding:0 6px; font-size:12px; }
.reason { width:100%; box-sizing:border-box; margin-top:6px; padding:3px 6px; font:inherit; border:1px solid var(--line); border-radius:4px; }
body.only-wrong .card:not(.wrong) { display:none; }
"""
INTERACTIVE_BAR = """<div class="bar"><b id="count">0 marked wrong</b>
<label><input type="checkbox" id="only"> only marked</label><button id="clear">Clear all</button><span id="status">click a card = wrong; type a reason; saved automatically</span></div>"""
INTERACTIVE_JS = """<script>
const marks = {}; const cards = [...document.querySelectorAll('.card[data-slug]')];
const st = document.getElementById('status'); let t;
function render() {
  cards.forEach(c => { const m = marks[c.dataset.slug]; c.classList.toggle('wrong', !!m);
    const i = c.querySelector('.reason'); if (m && document.activeElement !== i) i.value = m.reason || ''; });
  document.getElementById('count').textContent = Object.keys(marks).length + ' marked wrong';
}
function save() { clearTimeout(t); t = setTimeout(() => fetch('/marks', {method:'POST', body:JSON.stringify(marks)})
  .then(() => st.textContent = 'saved ' + new Date().toLocaleTimeString())
  .catch(() => st.textContent = 'SAVE FAILED: is the server running?'), 300); }
cards.forEach(c => {
  c.addEventListener('click', e => { if (e.target.closest('a,input')) return;
    const s = c.dataset.slug; if (marks[s]) delete marks[s]; else marks[s] = {reason: c.querySelector('.reason').value}; render(); save(); });
  c.querySelector('.reason').addEventListener('input', e => { marks[c.dataset.slug] = {reason: e.target.value}; render(); save(); });
});
document.getElementById('only').onchange = e => document.body.classList.toggle('only-wrong', e.target.checked);
document.getElementById('clear').onclick = () => { if (confirm('Clear all marks?')) { for (const k in marks) delete marks[k]; cards.forEach(c => c.querySelector('.reason').value=''); render(); save(); } };
fetch('/marks').then(r => r.json()).then(m => { Object.assign(marks, m); render(); });
</script>"""

def serve(page, recs, marks_path, port):
    """Serve the sheet; POST /marks stores {slug: {reason, + the record's colour facts}} in marks_path."""
    by_slug = {r["slug"]: r for r in recs}
    class H(BaseHTTPRequestHandler):
        def _send(self, body, ctype):
            data = body.encode("utf-8"); self.send_response(200)
            self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)
        def do_GET(self):
            if self.path == "/marks":
                self._send(marks_path.read_text(encoding="utf-8") if marks_path.exists() else "{}", "application/json")
            else:
                self._send(page, "text/html; charset=utf-8")
        def do_POST(self):
            marks = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            out = {s: {"reason": m.get("reason", ""), **{k: by_slug[s].get(k) for k in
                       ("brand", "material", "color_name", "hex", "measured_hex", "url", "local_image")}}
                   for s, m in marks.items() if s in by_slug}
            marks_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"saved {len(out)} marks → {marks_path}", flush=True)
            self._send("{}", "application/json")
        def log_message(self, *a): pass
    print(f"→ http://localhost:{port}/   (Ctrl-C to stop)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shop", help="only this shop (display name, e.g. Smart3D)")
    ap.add_argument("--brand", help="only brands matching this regex (case-insensitive), shows every card")
    ap.add_argument("--serve", action="store_true", help="serve the sheet locally; clicking a card marks it wrong, marks are saved to a file")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--all", action="store_true", help="every card, not flagged + sample")
    ap.add_argument("--ok-sample", type=int, default=60)
    ap.add_argument("--out", default=str(config.FILAMENTS_CACHE / "review_sheet.html"))
    ap.add_argument("--no-open", action="store_true", help="don't open the sheet in the browser")
    args = ap.parse_args()

    recs = [r for r in json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8"))
            if r.get("rgb") and r.get("local_image")
            and (not args.shop or r["shop"] == args.shop)
            and (not args.brand or re.search(args.brand, r["brand"], re.I))]
    if args.brand: args.all = True
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
    if args.brand: key = lambda x: (x[0]["material"], x[0]["color_name"].lower(), x[0]["brand"])
    flagged.sort(key=key); ok.sort(key=key)
    inter = args.serve
    cards = lambda items, **kw: "".join(card(r, w, interactive=inter, **kw) for r, w in items)

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
{INTERACTIVE_CSS if inter else ""}
</style></head><body>
{INTERACTIVE_BAR if inter else ""}
<h1>Measurement review</h1>
<p class="lead">Left: shop photo. Right: the colour <code>filament_rgb()</code> measured from it.
If the right square doesn't look like the filament, the measurement is wrong.
<b>box</b> = photo is mostly kraft cardboard (share &gt; {KRAFT_FLAG}); <b>cluster</b> = 3+ colours of one brand measure the same.
{len(recs)} filaments{(' in ' + html.escape(args.shop)) if args.shop else ''}, {len(flagged)} flagged.</p>
<h2>Changed by the last measurement ({len(changed)})</h2>
<p class="lead">Photo · colour before · colour now, biggest change first. Check that "now" matches the photo better.</p>
<div class="grid">{cards(changed, show_previous=True)}</div>
<h2>Flagged ({len(flagged)})</h2><div class="grid">{cards(flagged)}</div>
<h2>{'All' if args.all else 'Random sample of'} unflagged ({len(ok)})</h2><div class="grid">{cards(ok)}</div>
{INTERACTIVE_JS if inter else ""}</body></html>"""
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"→ {out}  ({len(flagged)} flagged, {len(ok)} ok shown, {out.stat().st_size // 1024} KB)")
    if args.serve:
        tag = re.sub(r"\W+", "_", args.brand or args.shop or "all").strip("_").lower()
        serve(page, recs, config.FILAMENTS_CACHE / f"review_marks_{tag}.json", args.port)
        return
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())

if __name__ == "__main__":
    main()
