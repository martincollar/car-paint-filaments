"""Order the root-page tile's factory two-tones by hand: drag cards to reorder, ✕ to drop one, + to add one from the pool
of all the car's combinations. The first card is the colour the tile rests on. "Save" writes `index.paints` of
cars/<car>/car.json and re-runs src/build_index.py. Saving is accepted from localhost only.

Usage: .venv/bin/python scripts/tile_combos.py [--car doppler] [--port 8770]
"""
import argparse, http.server, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import config
from build_index import best_pla

PAGE = """<!doctype html><meta charset=utf-8><title>Tile two-tones</title>
<style>
body{font:15px system-ui;margin:0;padding:24px;background:#f5f1e6;color:#222}
h2{margin:18px 0 8px} .bar{position:sticky;top:0;background:#f5f1e6;padding:8px 0;z-index:5}
button.save{font:600 15px system-ui;padding:8px 18px;border:2px solid #222;border-radius:999px;background:#2b8a7a;color:#fff;cursor:pointer}
#msg{margin-left:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
.card{background:#fff;border:2px solid #222;border-radius:10px;padding:8px;cursor:grab;position:relative;user-select:none}
.card.over{outline:3px dashed #2b8a7a}.card.first{background:#fff3c4}
.sw{display:flex;height:46px;border-radius:6px;overflow:hidden;border:1px solid #0004}
.sw i{flex:1}.code{font-weight:700}.n{font:12px system-ui;color:#555;margin-top:4px}
.x{position:absolute;top:4px;right:6px;border:0;background:none;font-size:18px;cursor:pointer}
.pool .card{cursor:pointer;opacity:.85}.pos{position:absolute;top:4px;left:8px;font:700 12px system-ui;color:#fff;text-shadow:0 0 3px #000}
</style>
<div class=bar><button class=save onclick=save()>Save</button><span id=msg></span>
<span style="margin-left:16px;color:#555">drag to reorder · first = resting colour · ✕ drops · click a pool card to add</span></div>
<h2>On the tile (<span id=cnt></span>)</h2><div class=grid id=cur></div>
<h2>Pool (other combinations)</h2><div class="grid pool" id=pool></div>
<script>
var ALL=__DATA__, cur=__CUR__, drag=null;
function card(c,i,inPool){var d=document.createElement('div');d.className='card'+(i===0&&!inPool?' first':'');
 d.innerHTML=(inPool?'':'<span class=pos>'+(i+1)+'</span><button class=x title=drop>✕</button>')+
 '<div class=sw><i style="background:'+c.upper_hex+'"></i><i style="background:'+c.lower_hex+'"></i></div>'+
 '<div class=code>'+c.code+' <small>'+c.year+'</small></div><div class=n>'+c.upper+' / '+c.lower+'<br>'+c.upper_label+' / '+c.lower_label+'</div>';return d}
function render(){var el=document.getElementById('cur'),pl=document.getElementById('pool');el.innerHTML='';pl.innerHTML='';
 document.getElementById('cnt').textContent=cur.length;
 cur.forEach(function(code,i){var c=ALL[code],d=card(c,i,false);d.draggable=true;
  d.querySelector('.x').onclick=function(){cur.splice(i,1);render()};
  d.ondragstart=function(){drag=i};d.ondragover=function(e){e.preventDefault();d.classList.add('over')};
  d.ondragleave=function(){d.classList.remove('over')};
  d.ondrop=function(e){e.preventDefault();var m=cur.splice(drag,1)[0];cur.splice(i,0,m);render()};el.appendChild(d)});
 Object.keys(ALL).filter(function(k){return cur.indexOf(k)<0}).forEach(function(k){var d=card(ALL[k],0,true);
  d.onclick=function(){cur.push(k);render()};pl.appendChild(d)})}
function save(){fetch('/__save',{method:'POST',body:JSON.stringify(cur)}).then(r=>r.json()).then(function(r){
 document.getElementById('msg').textContent=r.ok?'Saved, tile rebuilt.':'Error: '+r.error})}
render();
</script>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default="doppler")
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args()
    car = args.car
    matches = json.loads((config.car_data(car) / "matches.json").read_text(encoding="utf-8"))
    combos = json.loads((config.car_dir(car) / "combinations.json").read_text(encoding="utf-8"))
    car_json = config.car_dir(car) / "car.json"

    allc = {}
    for year, v in combos["years"].items():
        for c in v["combinations"]:
            if "unresolved" in c or "intermediate" in c:
                continue
            try:
                (up, _), (lo, _) = best_pla(matches, c["upper"]), best_pla(matches, c["lower"])
            except ValueError:
                continue
            allc[c["code"]] = {"code": c["code"], "year": year, "upper": c["upper"], "lower": c["lower"],
                               "upper_hex": up["hex"], "lower_hex": lo["hex"],
                               "upper_label": f'{up["brand"]} {up["color_name"]}', "lower_label": f'{lo["brand"]} {lo["color_name"]}'}
    paints = (json.loads(car_json.read_text(encoding="utf-8")).get("index") or {}).get("paints") or []
    cur = [p["combo"] for p in paints if isinstance(p, dict) and p.get("combo") in allc]

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, body, ctype):
            self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            page = PAGE.replace("__DATA__", json.dumps(allc)).replace("__CUR__", json.dumps(cur))
            self._send(page.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            if self.path != "/__save" or self.client_address[0] not in ("127.0.0.1", "::1"):
                self.send_error(403); return
            try:
                codes = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                assert all(c in allc for c in codes) and codes, "empty or unknown codes"
                meta = json.loads(car_json.read_text(encoding="utf-8"))
                keep = [p for p in meta["index"]["paints"] if not (isinstance(p, dict) and "combo" in p)]
                meta["index"]["paints"] = keep + [{"combo": c} for c in codes]
                car_json.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                done = subprocess.run([sys.executable, str(ROOT / "src" / "build_index.py")], cwd=ROOT, capture_output=True, text=True)
                if done.returncode:
                    raise RuntimeError(done.stderr.strip()[-400:])
                cur[:] = codes
                out = {"ok": True}
            except Exception as e:
                out = {"ok": False, "error": str(e)}
            self._send(json.dumps(out).encode(), "application/json")

        def log_message(self, *a):
            pass

    print(f"http://localhost:{args.port}/  ({len(cur)} on the tile, {len(allc) - len(cur)} in the pool)")
    http.server.ThreadingHTTPServer(("", args.port), H).serve_forever()


if __name__ == "__main__":
    main()
