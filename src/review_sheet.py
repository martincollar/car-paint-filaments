"""Visual check of filament measurements: product photo next to the measured colour.

Writes a self-contained HTML contact sheet (base64 thumbnails) so a human can
see at a glance where `filament_rgb()` measured the box, the spool or the
background instead of the filament.

A card is flagged when
  - box:     the photo is mostly kraft cardboard (`color_tools.kraft_share()` > 0.12)
             AND the measured colour itself looks like cardboard AND the name isn't
             a beige/brown family colour (those legitimately look like kraft), or
  - cluster: 3+ differently named colours of one brand and material in one shop measure within
             ΔE 2 of it (the photos show packaging, not the colour).
Manual overrides (`confidence: manual_override`) are never flagged.

Records whose colour moved by ΔE >= 3 in the last measure_filaments.py run carry
`previous_hex`; they get their own "Changed" section with old and new swatches.

Usage:
    python review_sheet.py                         # flagged first, then a sample of OK ones
    python review_sheet.py --shop Smart3D --all    # every Smart3D card
    python review_sheet.py --out /tmp/sheet.html --no-open
    python review_sheet.py --material ASA          # every ASA card, grouped by shop
    python review_sheet.py --brand lume            # served by default: click wrong cards + reason, saved to filaments/.cache/review_marks_<brand>.json
    python review_sheet.py --no-serve              # static page only (no reason boxes, opens the file)
"""
import argparse, collections, html, io, json, random, re, sys, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
import config
from color_tools import (_load, filament_rgb, delta_e_2000, delta_e_2000_many, hex_to_rgb, kraft_share,
                         kraft_like_rgb, kraft_like_name, rgb_to_lab)
from prepare_thumbnails import to_b64_jpg
from measure_filaments import measure_hints

KRAFT_FLAG = 0.12

def kraft_like_hex(hx):
    return kraft_like_rgb(hex_to_rgb(hx))

def cluster_flags(records):
    groups = collections.defaultdict(list)
    for r in records:
        if r.get("confidence") == "measured_dominant_hue":
            groups[(r["shop"], r["brand"], r["material"])].append(r)
    flagged = set()
    for members in groups.values():
        lab = rgb_to_lab([g["rgb"] for g in members])
        close = delta_e_2000_many(lab[:, None, :], lab[None, :, :]) < 2.0     # n × n, diagonal True
        for i, r in enumerate(members):
            near = {members[j]["color_name"] for j in np.flatnonzero(close[i])}
            if len(near | {r["color_name"]}) >= 3:
                flagged.add(r["slug"])
    return flagged

def overlay_b64(src, mask, max_dim=160):
    """The photo with every pixel filament_rgb() did NOT use dimmed to 18 % grey: what's left bright is what was measured."""
    im = Image.fromarray(_load(src)); im.thumbnail((max_dim, max_dim))
    m = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize(im.size, Image.NEAREST)) > 0
    a = np.asarray(im, dtype=np.float32)
    a[~m] = a[~m] * 0.18 + 128 * 0.82 * 0.18
    return to_b64_jpg(Image.fromarray(a.astype(np.uint8)), max_dim=max_dim, quality=74)

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
    overlay_img = (f'<img class="used" src="{r["_overlay"]}" alt="" title="pixels filament_rgb() measured (rest dimmed)'
                   + (f' → auto {r["measured_hex"]}, now manual {r["hex"]}' if r.get("confidence") == "manual_override" and r.get("measured_hex") else '')
                   + '">') if r.get("_overlay") else ""
    extra = ""
    if interactive:
        ov = f' · measured {r["measured_hex"]}' if r.get("measured_hex") else ""
        extra = (f'<br><span class="meta">{e(r["title"])}{ov}</span>'
                 f'<input class="reason" type="text" placeholder="reason (what it should be)" autocomplete="off">'
                 f'<button class="samplebtn" type="button">▣ sample colour</button>')
    return f"""<figure class="card{' flag' if why else ''}" data-slug="{e(r['slug'])}">
  <div class="{pair_cls}{' ov' if r.get('_overlay') else ''}"><img src="{thumb}" alt="">{overlay_img}{swatches}</div>
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
.samplebtn { margin-top:6px; font:inherit; font-size:12px; background:#fff; border:1px solid var(--line); border-radius:4px; padding:2px 8px; cursor:pointer; }
.card.fixed .sw:last-child { outline:3px solid #2e7d32; outline-offset:-3px; }
.card.fixed::before { content:"✓ override saved"; position:absolute; top:6px; left:8px; background:#2e7d32; color:#fff; border-radius:3px; padding:0 6px; font-size:12px; z-index:1; }
#sm { position:fixed; inset:0; background:rgba(20,16,10,.82); z-index:20; display:none; flex-direction:column; align-items:center; padding:12px; gap:8px; color:#fff; }
#sm.on { display:flex; }
#sm .stage { position:relative; flex:1; min-height:0; display:flex; }
#sm canvas { max-width:94vw; max-height:100%; object-fit:contain; display:block; cursor:crosshair; touch-action:none; background:#fff; }
#smbox { position:absolute; border:2px solid #ff2bd6; box-shadow:0 0 0 1px #fff inset, 0 0 0 9999px rgba(0,0,0,.35); cursor:move; box-sizing:border-box; touch-action:none; }
#smbox i { position:absolute; right:-7px; bottom:-7px; width:14px; height:14px; background:#ff2bd6; border:2px solid #fff; border-radius:3px; cursor:nwse-resize; }
#sm .bar2 { display:flex; gap:10px; align-items:center; flex-wrap:wrap; justify-content:center; }
#sm .bar2 button, #sm .bar2 input[type=text] { font:inherit; padding:4px 10px; border-radius:4px; border:0; }
#sm .bar2 input[type=text] { width:340px; max-width:80vw; }
#smsw { width:54px; height:34px; border-radius:5px; border:2px solid #fff; }
"""
INTERACTIVE_BAR = """<div class="bar"><b id="count">0 marked wrong</b>
<label><input type="checkbox" id="only"> only marked</label><button id="clear">Clear all</button><span id="status">click a card = wrong; type a reason; saved automatically</span></div>"""
SAMPLE_HTML = """<div id="sm"><div id="smtitle"></div><div class="stage"><canvas id="smc"></canvas><div id="smbox"><i></i></div></div>
<div class="bar2"><div id="smsw"></div><b id="smhex">–</b><span id="smold" style="opacity:.7"></span>
<label><input type="checkbox" id="smlit"> lit half only</label>
<input type="text" id="smnote" placeholder="note (optional)"><button id="smsave">Save override</button><button id="smcancel">Cancel</button></div></div>"""
SAMPLE_JS = """
const sm = document.getElementById('sm'), smc = document.getElementById('smc'), box = document.getElementById('smbox');
let smSlug = null, smCard = null, smImg = null, smHex = null, smPix = null;   // box in canvas-display px: bx,by,bw,bh
let bx = 0, by = 0, bw = 0, bh = 0;
function layoutBox() { box.style.left = bx + 'px'; box.style.top = by + 'px'; box.style.width = bw + 'px'; box.style.height = bh + 'px'; measure(); }
function measure() {
  if (!smPix) return;
  const k = smc.width / smc.clientWidth, x0 = Math.max(0, Math.round(bx * k)), y0 = Math.max(0, Math.round(by * k));
  const x1 = Math.min(smc.width, Math.round((bx + bw) * k)), y1 = Math.min(smc.height, Math.round((by + bh) * k));
  let px = [];
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { const i = (y * smc.width + x) * 4; px.push([smPix[i], smPix[i+1], smPix[i+2]]); }
  if (!px.length) return;
  if (document.getElementById('smlit').checked) {
    const v = px.map(p => p[0] + p[1] + p[2]).sort((a, b) => a - b), med = v[v.length >> 1];
    px = px.filter(p => p[0] + p[1] + p[2] >= med);
  }
  const med = c => { const a = px.map(p => p[c]).sort((m, n) => m - n); return a[a.length >> 1]; };
  smHex = '#' + [0,1,2].map(c => med(c).toString(16).padStart(2, '0')).join('').toUpperCase();
  document.getElementById('smsw').style.background = smHex;
  document.getElementById('smhex').textContent = smHex + ' (' + px.length + ' px)';
}
function openSample(card) {
  smCard = card; smSlug = card.dataset.slug;
  document.getElementById('smtitle').textContent = card.querySelector('figcaption b').nextSibling.textContent.trim() + ' · ' + card.querySelector('figcaption').innerText.split('\\n')[0];
  document.getElementById('smold').textContent = 'now ' + card.querySelector('.sw:last-child').title.replace(/^now /, '');
  document.getElementById('smnote').value = card.querySelector('.reason').value || '';
  smImg = new Image();
  smImg.onload = () => {
    const mx = innerWidth * .94, my = innerHeight - 130, sc = Math.min(1, mx / smImg.width, my / smImg.height);
    smc.width = smImg.width; smc.height = smImg.height;
    smc.style.width = Math.round(smImg.width * sc) + 'px'; smc.style.height = Math.round(smImg.height * sc) + 'px';
    const ctx = smc.getContext('2d', {willReadFrequently: true}); ctx.drawImage(smImg, 0, 0);
    smPix = ctx.getImageData(0, 0, smc.width, smc.height).data;
    bw = bh = Math.round(smc.clientWidth * .12); bx = Math.round(smc.clientWidth / 2 - bw / 2); by = Math.round(smc.clientHeight / 2 - bh / 2); layoutBox();
  };
  smImg.src = '/img/' + encodeURIComponent(smSlug); sm.classList.add('on');
}
function pt(e) { const r = smc.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
let drag = null;
box.addEventListener('pointerdown', e => { e.stopPropagation(); box.setPointerCapture(e.pointerId); const [x, y] = pt(e);
  drag = e.target.tagName === 'I' ? {m: 'rs'} : {m: 'mv', dx: x - bx, dy: y - by}; });
smc.addEventListener('pointerdown', e => { smc.setPointerCapture(e.pointerId); const [x, y] = pt(e); bx = x; by = y; bw = bh = 4; drag = {m: 'new', x0: x, y0: y}; layoutBox(); });
const mover = e => { if (!drag) return; const [x, y] = pt(e), W = smc.clientWidth, H = smc.clientHeight;
  if (drag.m === 'mv') { bx = Math.min(Math.max(0, x - drag.dx), W - bw); by = Math.min(Math.max(0, y - drag.dy), H - bh); }
  else if (drag.m === 'rs') { bw = Math.max(4, Math.min(x - bx, W - bx)); bh = Math.max(4, Math.min(y - by, H - by)); }
  else { bx = Math.max(0, Math.min(x, drag.x0)); by = Math.max(0, Math.min(y, drag.y0)); bw = Math.max(4, Math.min(W, Math.max(x, drag.x0)) - bx); bh = Math.max(4, Math.min(H, Math.max(y, drag.y0)) - by); }
  layoutBox(); };
box.addEventListener('pointermove', mover); smc.addEventListener('pointermove', mover);
addEventListener('pointerup', () => drag = null);
document.getElementById('smlit').onchange = measure;
document.getElementById('smcancel').onclick = () => sm.classList.remove('on');
addEventListener('keydown', e => { if (e.key === 'Escape') sm.classList.remove('on'); });
document.getElementById('smsave').onclick = () => {
  const note = document.getElementById('smnote').value.trim();
  fetch('/override', {method: 'POST', body: JSON.stringify({slug: smSlug, hex: smHex, note, lit: document.getElementById('smlit').checked})})
    .then(r => r.json()).then(() => { smCard.classList.add('fixed'); smCard.querySelector('.sw:last-child').style.background = smHex;
      smCard.querySelector('.sw:last-child').title = 'now ' + smHex; sm.classList.remove('on'); st.textContent = 'override ' + smHex + ' saved: run measure_filaments.py to apply'; })
    .catch(() => st.textContent = 'OVERRIDE SAVE FAILED');
};
cards.forEach(c => { const b = c.querySelector('.samplebtn'); if (b) b.addEventListener('click', e => { e.stopPropagation(); openSample(c); }); });
"""
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
  c.addEventListener('click', e => { if (e.target.closest('a,input,button')) return;
    const s = c.dataset.slug; if (marks[s]) delete marks[s]; else marks[s] = {reason: c.querySelector('.reason').value}; render(); save(); });
  c.querySelector('.reason').addEventListener('input', e => { marks[c.dataset.slug] = {reason: e.target.value}; render(); save(); });
});
document.getElementById('only').onchange = e => document.body.classList.toggle('only-wrong', e.target.checked);
document.getElementById('clear').onclick = () => { if (confirm('Clear all marks?')) { for (const k in marks) delete marks[k]; cards.forEach(c => c.querySelector('.reason').value=''); render(); save(); } };
fetch('/marks').then(r => r.json()).then(m => { Object.assign(marks, m); render(); });
""" + SAMPLE_JS + """</script>"""

def serve(page, recs, marks_path, port):
    """Serve the sheet; POST /marks stores {slug: {reason, + the record's colour facts}} in marks_path."""
    by_slug = {r["slug"]: r for r in recs}
    class H(BaseHTTPRequestHandler):
        def _send(self, body, ctype):
            data = body if isinstance(body, bytes) else body.encode("utf-8"); self.send_response(200)
            self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)
        def do_GET(self):
            if self.path.startswith("/img/"):
                r = by_slug.get(urllib.parse.unquote(self.path[5:]))
                src = config.FILAMENTS_SOURCES / r["local_image"] if r else None
                if not src or not src.exists():
                    self.send_error(404); return
                im = Image.fromarray(_load(src)); im.thumbnail((1600, 1600))
                buf = io.BytesIO(); im.save(buf, "PNG"); self._send(buf.getvalue(), "image/png")
            elif self.path == "/marks":
                self._send(marks_path.read_text(encoding="utf-8") if marks_path.exists() else "{}", "application/json")
            else:
                self._send(page, "text/html; charset=utf-8")
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/override":
                r = by_slug.get(body.get("slug"))
                if not r or not re.fullmatch(r"#[0-9A-Fa-f]{6}", body.get("hex", "")):
                    self.send_error(400); return
                ovp = config.FILAMENT_COLOR_OVERRIDES
                ov = json.loads(ovp.read_text(encoding="utf-8")) if ovp.exists() else {}
                how = "lit half of" if body.get("lit") else "median of"
                ov[r["slug"]] = {"hex": body["hex"].upper(),
                                 "note": f"Hex = {how} a box sampled by hand on the review page."
                                         + (f" {body['note']}" if body.get("note") else "")}
                ovp.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"override {r['slug']} → {body['hex'].upper()}", flush=True)
                self._send("{}", "application/json"); return
            marks = body
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
    ap.add_argument("--material", help="only this material (PLA, PLA+, PETG, ASA), shows every card")
    ap.add_argument("--unsampled", action="store_true",
                    help="hide cards you already fixed with the sample square (override note says 'sampled by hand on the review page'); marks go to their own file")
    ap.add_argument("--serve", action=argparse.BooleanOptionalAction, default=True,
                    help="serve the sheet locally (default; --no-serve writes a static page): clicking a card marks it wrong, marks are saved to a file")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--overlay", action=argparse.BooleanOptionalAction, default=None,
                    help="draw the pixels filament_rgb() measured next to each photo (default: on up to 400 cards)")
    ap.add_argument("--all", action="store_true", help="every card, not flagged + sample")
    ap.add_argument("--ok-sample", type=int, default=60)
    ap.add_argument("--out", default=str(config.FILAMENTS_CACHE / "review_sheet.html"))
    ap.add_argument("--no-open", action="store_true", help="don't open the sheet in the browser")
    args = ap.parse_args()

    ov = json.loads(config.FILAMENT_COLOR_OVERRIDES.read_text(encoding="utf-8")) if config.FILAMENT_COLOR_OVERRIDES.exists() else {}
    sampled = {slug for slug, o in ov.items() if "sampled by hand on the review page" in o.get("note", "")}
    recs = [r for r in json.loads(config.FILAMENTS_JSON.read_text(encoding="utf-8"))
            if r.get("rgb") and r.get("local_image")
            and (not args.shop or r["shop"] == args.shop)
            and (not args.brand or re.search(args.brand, r["brand"], re.I))
            and (not args.material or r["material"].lower() == args.material.lower())
            and not (args.unsampled and r["slug"] in sampled)]
    if args.brand or args.material: args.all = True
    print(f"{len(recs)} filaments: looking for same-colour clusters…", flush=True)
    overlay = args.overlay if args.overlay is not None else len(recs) <= 400
    clusters = cluster_flags(recs)
    flagged, ok = [], []
    for i, r in enumerate(recs, 1):
        if i % 200 == 0 or i == len(recs):
            print(f"  checked {i}/{len(recs)} photos", flush=True)
        src = config.FILAMENTS_SOURCES / r["local_image"]
        r["_kraft"] = kraft_share(src) if src.exists() else 0.0
        if overlay and src.exists():
            trace = {}
            filament_rgb(src, name=r.get("color_name"), trace=trace, **measure_hints(r.get("brand")))
            if "mask" in trace: r["_overlay"] = overlay_b64(src, trace["mask"])
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
.pair.ov {{ grid-template-columns:1fr 1fr 0.5fr; }}
.pair.three.ov {{ grid-template-columns:2fr 2fr 1fr 1fr; }}
.pair img.used {{ outline:1px dashed var(--muted); outline-offset:-1px; }}
.pair img {{ width:100%; height:120px; object-fit:contain; background:#fff; }}
.sw.old {{ opacity:.9; outline:2px dashed rgba(0,0,0,.25); outline-offset:-4px; }}
.sw {{ border-radius:6px; border:1px solid rgba(0,0,0,.12); }}
figcaption {{ margin-top:6px; font-size:12.5px; }}
.meta {{ color:var(--muted); font-variant-numeric:tabular-nums; }}
.tag {{ display:inline-block; background:var(--bad); color:#fff; border-radius:3px; padding:0 5px; font-size:11px; margin-left:3px; }}
a {{ color:var(--ink); }}
{INTERACTIVE_CSS if inter else ""}
</style></head><body>
{INTERACTIVE_BAR + SAMPLE_HTML if inter else ""}
<h1>Measurement review</h1>
<p class="lead">Left: shop photo. Right: the colour <code>filament_rgb()</code> measured from it.
If the right square doesn't look like the filament, the measurement is wrong.
{"The dark-dimmed middle picture shows the pixels <code>filament_rgb()</code> took the colour from (everything dimmed was ignored): if it lit up the spool, box or background, the measurement is wrong. " if overlay else ""}<b>box</b> = photo is mostly kraft cardboard (share &gt; {KRAFT_FLAG}); <b>cluster</b> = 3+ colours of one brand measure the same.
{len(recs)} {html.escape(args.material or '')} filaments{(' in ' + html.escape(args.shop)) if args.shop else ''}, {len(flagged)} flagged.</p>
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
        tag = re.sub(r"\W+", "_", (args.brand or args.material or args.shop or "all") + ("_unsampled" if args.unsampled else "")).strip("_").lower()
        serve(page, recs, config.FILAMENTS_CACHE / f"review_marks_{tag}.json", args.port)
        return
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())

if __name__ == "__main__":
    main()
