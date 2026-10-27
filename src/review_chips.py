"""Review a car's colour chips next to their measured hex, and override by hand.

Shows one card per colour: the scanned chip, a reference-car image, the measured
swatch + hex (ΔE vs the RAL/placeholder guess), and three ways to change it —
type a hex, pick a colour, or drag a box on the chip to re-measure its median.
Saves to cars/<car>/chip_overrides.json as {chip_key: {hex, name, code, note}}.
Nothing is applied to the pipeline here; this is a review/decision step.

    python src/review_chips.py --car unimog406            # serve + open
    python src/review_chips.py --car unimog406 --port 8771 --no-open

The chips live in cars/<car>/sources/chips/<key>.jpg and the measurements in
cars/<car>/data/chip_measurements.json (see measure_chips.py / SOURCES.md).
"""
from __future__ import annotations
import argparse, base64, html, json, mimetypes, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config


def data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def load(car: str):
    meas_path = config.car_data(car) / "chip_measurements.json"
    rows = json.loads(meas_path.read_text(encoding="utf-8"))
    ov_path = config.car_dir(car) / "chip_overrides.json"
    ov = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
    real_path = config.car_data(car) / "real_car_matches.json"
    real = json.loads(real_path.read_text(encoding="utf-8"))["matches"] if real_path.exists() else {}
    chips = config.car_sources(car) / "chips"
    refs = config.car_sources(car) / "refcars"
    photos = config.car_sources(car) / "photos"
    for r in rows:
        r["chip_uri"] = data_uri(chips / f"{r['key']}.jpg")
        r["ref_uri"] = data_uri(refs / f"404{r['key']}.gif")
        o = ov.get(r["key"])
        r["override"] = o["hex"].upper() if o else ""
        r["override_note"] = o.get("note", "") if o else ""
        rc = real.get(r["key"], {})
        r["real_uri"] = data_uri(photos / rc["file"]) if rc.get("file") else ""
        r["real_confidence"] = rc.get("confidence", "")
        r["real_note"] = rc.get("note", "")
        r["real_credit"] = f'{rc.get("commons","")} · {rc.get("author","")} · {rc.get("licence","")}' if rc.get("file") else ""
    return rows, ov_path


CSS = """
:root{--line:#d9d6cf;--muted:#6b6b66}
*{box-sizing:border-box}
body{font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f3f1ea;color:#1c1c1a}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);padding:12px 18px;z-index:5}
header h1{font-size:17px;margin:0 0 2px}
header p{margin:0;color:var(--muted);font-size:13px}
#status{font-size:13px;color:#2e7d32;min-height:18px;margin-top:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:14px;padding:16px 18px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px;position:relative}
.card.changed{border-color:#2e7d32;box-shadow:0 0 0 1px #2e7d32}
.hd{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.hd b{font-size:14px}.hd .code{color:var(--muted);font-size:12px}
.imgs{display:flex;gap:8px;margin:8px 0;flex-wrap:wrap}
.chipwrap{position:relative;flex:0 0 auto;line-height:0}
.chip{width:130px;height:auto;border:1px solid var(--line);border-radius:4px;cursor:crosshair;touch-action:none}
.ref{height:80px;width:auto;border:1px solid var(--line);border-radius:4px}
.selbox{position:absolute;border:1.5px solid #fff;outline:1px solid #000;background:rgba(255,255,255,.12);pointer-events:none;display:none}
.realwrap{flex:1 1 160px;min-width:160px}
.real{width:100%;max-height:140px;object-fit:cover;border:1px solid var(--line);border-radius:4px;display:block}
.real-missing{width:100%;min-height:80px;border:1px dashed var(--line);border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:12px;color:var(--muted);text-align:center;padding:8px}
.real-tag{display:inline-block;font-size:10px;border-radius:3px;padding:0 5px;margin-top:3px}
.real-tag.good{background:#e3f2e3;color:#1b5e20}
.real-tag.tentative{background:#fde9c8;color:#8a5a00}
.real-note{font-size:11px;color:var(--muted);margin-top:3px;line-height:1.35}
.real-credit{font-size:10px;color:#9a9890;margin-top:2px}
.swatches{display:flex;gap:0;border:1px solid var(--line);border-radius:5px;overflow:hidden;height:40px;margin:6px 0}
.swatches .sw{flex:1;display:flex;align-items:flex-end;justify-content:center;font-size:10px;padding:2px}
.sw .lbl{background:rgba(255,255,255,.82);border-radius:2px;padding:0 3px;color:#111}
.de{font-size:12px;color:var(--muted)}
.row{display:flex;gap:6px;align-items:center;margin-top:8px;flex-wrap:wrap}
input[type=text]{font:inherit;font-size:13px;border:1px solid var(--line);border-radius:4px;padding:4px 6px}
input#noteI{flex:1;min-width:120px}
input.hexI{width:92px;font-family:ui-monospace,Menlo,monospace;text-transform:uppercase}
input[type=color]{width:34px;height:30px;border:1px solid var(--line);border-radius:4px;background:#fff;padding:1px;cursor:pointer}
button{font:inherit;font-size:13px;border:1px solid var(--line);background:#fff;border-radius:5px;padding:4px 10px;cursor:pointer}
button.save{background:#2e7d32;color:#fff;border-color:#2e7d32}
button.reset{color:#b23}
.hint{font-size:12px;color:var(--muted);margin-top:4px}
.flag{display:inline-block;font-size:11px;background:#fde9c8;color:#8a5a00;border-radius:3px;padding:0 6px;margin-left:6px}
"""

JS = """
function hex2(n){return n.toString(16).padStart(2,'0').toUpperCase();}
function medianOfBox(img, bx){
  const c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;
  const g=c.getContext('2d');g.drawImage(img,0,0);
  const sx=img.naturalWidth/img.clientWidth, sy=img.naturalHeight/img.clientHeight;
  let x0=Math.round(bx.x*sx),y0=Math.round(bx.y*sy),w=Math.max(1,Math.round(bx.w*sx)),h=Math.max(1,Math.round(bx.h*sy));
  x0=Math.max(0,Math.min(x0,c.width-1));y0=Math.max(0,Math.min(y0,c.height-1));
  w=Math.min(w,c.width-x0);h=Math.min(h,c.height-y0);
  const d=g.getImageData(x0,y0,w,h).data, R=[],G=[],B=[];
  for(let i=0;i<d.length;i+=4){R.push(d[i]);G.push(d[i+1]);B.push(d[i+2]);}
  const med=a=>{a.sort((p,q)=>p-q);return a[a.length>>1];};
  return '#'+hex2(med(R))+hex2(med(G))+hex2(med(B));
}
function setCurrent(card,hex){
  hex=hex.toUpperCase();
  card.querySelector('.cur').style.background=hex;
  card.querySelector('.cur .lbl').textContent=hex;
  card.querySelector('.hexI').value=hex;
  card.querySelector('input[type=color]').value=hex;
  card.classList.add('changed');
}
function wire(card){
  const key=card.dataset.key;
  const img=card.querySelector('.chip'), box=card.querySelector('.selbox');
  let drag=null;
  const pt=e=>{const r=img.getBoundingClientRect();const t=e.touches?e.touches[0]:e;return{x:t.clientX-r.left,y:t.clientY-r.top};};
  img.addEventListener('pointerdown',e=>{e.preventDefault();drag=pt(e);box.style.display='block';box.style.left=drag.x+'px';box.style.top=drag.y+'px';box.style.width='0px';box.style.height='0px';});
  img.addEventListener('pointermove',e=>{if(!drag)return;const p=pt(e);const x=Math.min(p.x,drag.x),y=Math.min(p.y,drag.y),w=Math.abs(p.x-drag.x),h=Math.abs(p.y-drag.y);box.style.left=x+'px';box.style.top=y+'px';box.style.width=w+'px';box.style.height=h+'px';});
  const end=e=>{if(!drag)return;const p=pt(e);const bx={x:Math.min(p.x,drag.x),y:Math.min(p.y,drag.y),w:Math.abs(p.x-drag.x),h:Math.abs(p.y-drag.y)};drag=null;if(bx.w<3||bx.h<3){box.style.display='none';return;}const hex=medianOfBox(img,bx);setCurrent(card,hex);card.querySelector('.hint').textContent='sampled '+hex+' from the box — Save to keep';};
  img.addEventListener('pointerup',end);img.addEventListener('pointerleave',end);
  card.querySelector('input[type=color]').addEventListener('input',e=>{setCurrent(card,e.target.value);card.querySelector('.hint').textContent='picked — Save to keep';});
  card.querySelector('.hexI').addEventListener('change',e=>{let v=e.target.value.trim();if(!v.startsWith('#'))v='#'+v;if(/^#[0-9a-fA-F]{6}$/.test(v)){setCurrent(card,v);card.querySelector('.hint').textContent='typed — Save to keep';}else{card.querySelector('.hint').textContent='not a 6-digit hex';}});
  card.querySelector('.save').addEventListener('click',()=>{
    const hex=card.querySelector('.hexI').value, note=card.querySelector('#noteI'+key).value;
    post({key,hex,name:card.dataset.name,code:card.dataset.code,note},card,'saved '+hex);});
  card.querySelector('.reset').addEventListener('click',()=>{post({key,reset:true},card,'override removed; back to measured');});
}
function post(body,card,ok){
  const st=document.getElementById('status');
  fetch('/override',{method:'POST',body:JSON.stringify(body)}).then(r=>r.json()).then(()=>{
    st.textContent=card.dataset.name+': '+ok;
    if(body.reset){const m=card.dataset.measured;setCurrent(card,m);card.classList.remove('changed');card.querySelector('.hint').textContent='';}
  }).catch(()=>st.textContent='SAVE FAILED: is the server running?');
}
document.querySelectorAll('.card').forEach(wire);
"""


def card_html(r) -> str:
    name = html.escape(r["name"]); code = html.escape(r["code"])
    ral = f' · {html.escape(r["ral"])}' if r.get("ral") else ""
    meas = r["measured"].upper()
    cur = r["override"] or meas
    de = r.get("deltaE")
    flag = ' <span class="flag">check scan</span>' if isinstance(de, (int, float)) and de >= 6 else ""
    changed = " changed" if r["override"] else ""
    ref = f'<img class="ref" src="{r["ref_uri"]}" alt="reference car">' if r["ref_uri"] else ""
    note = html.escape(r["override_note"])
    if r["real_uri"]:
        tag = html.escape(r["real_confidence"])
        real_block = (
            f'<div class="realwrap"><img class="real" src="{r["real_uri"]}" alt="real car in this colour">'
            f'<span class="real-tag {tag}">{tag} match</span>'
            f'<div class="real-note">{html.escape(r["real_note"])}</div>'
            f'<div class="real-credit">{html.escape(r["real_credit"])}</div></div>'
        )
    else:
        real_note = html.escape(r["real_note"]) if r["real_note"] else "No credible real-car photo found for this colour."
        real_block = f'<div class="realwrap"><div class="real-missing">{real_note}</div></div>'
    return f"""
<div class="card{changed}" data-key="{r['key']}" data-name="{name}" data-code="{code}" data-measured="{meas}">
 <div class="hd"><b>{name}{flag}</b><span class="code">{code}{ral}</span></div>
 <div class="imgs">
   <div class="chipwrap"><img class="chip" src="{r['chip_uri']}" alt="chip scan"><div class="selbox"></div></div>
   {ref}
   {real_block}
 </div>
 <div class="swatches">
   <div class="sw" style="background:{meas}"><span class="lbl">measured {meas}</span></div>
   <div class="sw cur" style="background:{cur}"><span class="lbl">{cur}</span></div>
 </div>
 <div class="de">ΔE vs RAL/placeholder guess: {de}{'  · override set' if r['override'] else ''}</div>
 <div class="row">
   <input type="color" value="{cur}">
   <input type="text" class="hexI" value="{cur}">
   <input type="text" id="noteI{r['key']}" placeholder="note (optional)" value="{note}">
 </div>
 <div class="row">
   <button class="save">Save</button>
   <button class="reset">Reset to measured</button>
 </div>
 <div class="hint"></div>
</div>"""


def build_page(car, rows) -> str:
    cards = "\n".join(card_html(r) for r in rows)
    disp = config.car_meta(car).get("display", car)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chip review — {html.escape(disp)}</title><style>{CSS}</style></head><body>
<header><h1>Chip review — {html.escape(disp)}</h1>
<p>Chip scan, reference-car mockup, and (where found) a real car photographed in this colour — "no match found" means I couldn't find one, not that one doesn't exist. Drag a box on the chip to re-measure, or type/pick a hex. Save writes cars/{car}/chip_overrides.json. Nothing is applied to the pipeline yet.</p>
<div id="status"></div></header>
<div class="grid">{cards}</div>
<script>{JS}</script></body></html>"""


def serve(car, ov_path, port):
    def render():
        rows, _ = load(car)
        return build_page(car, rows)

    class H(BaseHTTPRequestHandler):
        def _send(self, body, ctype="text/html; charset=utf-8", code=200):
            b = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code); self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b))); self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(render())
            else:
                self._send("not found", code=404)

        def do_POST(self):
            if self.path != "/override":
                self._send("{}", "application/json", 404); return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            ov = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
            key = body["key"]
            if body.get("reset"):
                ov.pop(key, None)
                print(f"reset {key}", flush=True)
            else:
                hexv = body["hex"].upper()
                ov[key] = {"hex": hexv, "name": body.get("name", ""),
                           "code": body.get("code", ""),
                           "note": body.get("note", "") or "set by hand on the chip review page"}
                print(f"override {key} → {hexv}", flush=True)
            config.write_json(ov_path, ov)
            self._send(json.dumps({"ok": True}), "application/json")

        def log_message(self, *a): pass

    print(f"→ http://localhost:{port}/   (Ctrl-C to stop)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--out", help="also write a static copy of the page here")
    args = ap.parse_args()

    rows, ov_path = load(args.car)
    if args.out:
        Path(args.out).write_text(build_page(args.car, rows), encoding="utf-8")
        print("wrote", args.out)
    if not args.no_open:
        webbrowser.open(f"http://localhost:{args.port}/")
    serve(args.car, ov_path, args.port)


if __name__ == "__main__":
    main()
