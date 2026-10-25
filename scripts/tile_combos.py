"""Order the root-page tile's factory two-tones by hand: every card shows the car in that combination; drag to reorder,
✕ to drop one, click a pool card to add one from all the car's combinations, and pick each car's roof colour (upper,
lower, white or any colour). The first card is the colour the tile rests on. "Save" writes `index.paints` of
cars/<car>/car.json and re-runs src/build_index.py. Saving is accepted from localhost only.

Usage: .venv/bin/python scripts/tile_combos.py [--car doppler] [--port 8770]
"""
import argparse, base64, http.server, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import config
from build_index import best_pla, collect_car

PAGE = """<!doctype html><meta charset=utf-8><title>Tile two-tones</title>
<style>
body{font:15px system-ui;margin:0;padding:24px;background:#f5f1e6;color:#222}
h2{margin:18px 0 8px} .bar{position:sticky;top:0;background:#f5f1e6;padding:8px 0;z-index:5}
button.save{font:600 15px system-ui;padding:8px 18px;border:2px solid #222;border-radius:999px;background:#2b8a7a;color:#fff;cursor:pointer}
#msg{margin-left:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.card{background:#fff;border:2px solid #222;border-radius:10px;padding:8px;cursor:grab;position:relative;user-select:none}
.card.over{outline:3px dashed #2b8a7a}.card.first{background:#fff3c4}
canvas{width:100%;display:block}
.sw{display:flex;height:16px;border-radius:4px;overflow:hidden;border:1px solid #0004;margin-top:4px}
.sw i{flex:1}.code{font-weight:700;margin-top:4px}.n{font:12px system-ui;color:#555;margin-top:2px}
.x{position:absolute;top:4px;right:6px;border:0;background:none;font-size:18px;cursor:pointer}
.roof{display:flex;gap:4px;align-items:center;margin-top:6px;font:12px system-ui}
.roof b{font-weight:600;margin-right:2px}
.roof button{border:2px solid #0006;border-radius:6px;width:26px;height:22px;cursor:pointer;padding:0}
.roof button.on{border-color:#000;box-shadow:0 0 0 2px #2b8a7a}
.roof input{width:30px;height:24px;padding:0;border:0;background:none;cursor:pointer}
.pool .card{cursor:pointer;opacity:.9}.pos{position:absolute;top:6px;left:10px;font:700 13px system-ui;color:#fff;text-shadow:0 0 3px #000;z-index:2}
</style>
<div class=bar><button class=save onclick=save()>Save</button><span id=msg></span>
<span style="margin-left:16px;color:#555">drag to reorder · first = resting colour · ✕ drops · roof: pick under each car · click a pool card to add</span></div>
<h2>On the tile (<span id=cnt></span>)</h2><div class=grid id=cur></div>
<h2>Pool (other combinations)</h2><div class="grid pool" id=pool></div>
<script>
var ALL=__DATA__, cur=__CUR__, drag=null, R=null;
var M=[[0.4124564,0.3575761,0.1804375],[0.2126729,0.7151522,0.0721750],[0.0193339,0.1191920,0.9503041]],
 Mi=[[3.2404542,-1.5371385,-0.4985314],[-0.9692660,1.8760108,0.0415560],[0.0556434,-0.2040259,1.0572252]],WP=[0.95047,1,1.08883],BG=247;
function lin(c){c/=255;return c>0.04045?Math.pow((c+0.055)/1.055,2.4):c/12.92}
function gam(c){c=c<=0.0031308?12.92*c:1.055*Math.pow(c,1/2.4)-0.055;return Math.max(0,Math.min(1,c))*255}
function f(t){return t>216/24389?Math.cbrt(t):(24389/27*t+16)/116}
function finv(t){var t3=t*t*t;return t3>216/24389?t3:(116*t-16)/(24389/27)}
function toLab(r,g,b){r=lin(r);g=lin(g);b=lin(b);var fx=f((M[0][0]*r+M[0][1]*g+M[0][2]*b)/WP[0]),fy=f(M[1][0]*r+M[1][1]*g+M[1][2]*b),fz=f((M[2][0]*r+M[2][1]*g+M[2][2]*b)/WP[2]);return[116*fy-16,500*(fx-fy),200*(fy-fz)]}
function hexRgb(h){return[1,3,5].map(function(i){return parseInt(h.substr(i,2),16)})}
function lab(h){return toLab.apply(null,hexRgb(h))}
function img(src){return new Promise(function(ok){var i=new Image();i.onload=function(){ok(i)};i.src=src})}
Promise.all([img('/img/fg'),img('/img/mask'),img('/img/cut')]).then(function(a){
 var W=a[0].width,H=a[0].height,c=document.createElement('canvas');c.width=W;c.height=H;var x=c.getContext('2d',{willReadFrequently:true});
 x.drawImage(a[0],0,0);var base=x.getImageData(0,0,W,H),px=base.data;
 x.clearRect(0,0,W,H);x.drawImage(a[1],0,0);var mk=x.getImageData(0,0,W,H).data;
 x.clearRect(0,0,W,H);x.drawImage(a[2],0,0);var ct=x.getImageData(0,0,W,H).data,n=W*H,j,k;
 for(j=0;j<px.length;j+=4){for(k=0;k<3;k++)px[j+k]=Math.min(255,px[j+k]*255/BG);px[j+3]=ct[j]}
 var idx=[];for(var i=0;i<n;i++)if(mk[4*i]||mk[4*i+1]||mk[4*i+2])idx.push(i);
 var m=new Float32Array(idx.length*3),L=new Float32Array(idx.length),sum=[0,0,0],wt=[0,0,0];
 for(var q=0;q<idx.length;q++){i=idx[q];L[q]=toLab(px[4*i],px[4*i+1],px[4*i+2])[0];
  for(k=0;k<3;k++){var al=mk[4*i+k]/255;m[3*q+k]=al;sum[k]+=al*L[q];wt[k]+=al}}
 R={W:W,H:H,base:base,idx:idx,m:m,L:L,Lm:[0,1,2].map(function(z){return wt[z]?sum[z]/wt[z]:50})};render()});
function paint(cv,up,lo,roof){var o=new ImageData(new Uint8ClampedArray(R.base.data),R.W,R.H),px=o.data,src=R.base.data,
 tz=[lab(up),lab(roof),lab(lo)];
 for(var q=0;q<R.idx.length;q++){var i=R.idx[q],m=R.m,kk=m[3*q+1]>m[3*q]?1:0;if(m[3*q+2]>m[3*q+kk])kk=2;
  var tg=tz[kk],a=m[3*q+kk],dev=R.L[q]-R.Lm[kk];
  dev*=dev>0?Math.min(1,(100-tg[0])/(100-R.Lm[kk])):Math.min(1,tg[0]/R.Lm[kk]);
  var ly=(Math.max(0,Math.min(100,tg[0]+dev))+16)/116,fx=ly+tg[1]/500,fz=ly-tg[2]/200,X=finv(fx)*WP[0],Y=finv(ly),Z=finv(fz)*WP[2];
  px[4*i]=src[4*i]*(1-a)+gam(Mi[0][0]*X+Mi[0][1]*Y+Mi[0][2]*Z)*a;
  px[4*i+1]=src[4*i+1]*(1-a)+gam(Mi[1][0]*X+Mi[1][1]*Y+Mi[1][2]*Z)*a;
  px[4*i+2]=src[4*i+2]*(1-a)+gam(Mi[2][0]*X+Mi[2][1]*Y+Mi[2][2]*Z)*a}
 var t=document.createElement('canvas');t.width=R.W;t.height=R.H;t.getContext('2d').putImageData(o,0,0);
 cv.width=R.W/2;cv.height=R.H/2;var x=cv.getContext('2d');x.fillStyle='#fff';x.fillRect(0,0,cv.width,cv.height);x.drawImage(t,0,0,cv.width,cv.height)}
function roofHex(c,r){return r==='upper'?c.upper_hex:r==='lower'?c.lower_hex:r==='white'?'#F2F2F2':r}
function card(e,i,inPool){var c=ALL[e.code],d=document.createElement('div');d.className='card'+(i===0&&!inPool?' first':'');
 d.innerHTML=(inPool?'':'<span class=pos>'+(i+1)+'</span><button class=x title=drop>✕</button>')+'<canvas></canvas>'+
 '<div class=sw><i style="background:'+c.upper_hex+'"></i><i style="background:'+c.lower_hex+'"></i></div>'+
 '<div class=code>'+c.code+' <small>'+c.year+'</small></div><div class=n>'+c.upper+' / '+c.lower+'<br>'+c.upper_label+' / '+c.lower_label+'</div>'+
 (inPool?'':'<div class=roof><b>Roof</b></div>');
 if(R)paint(d.querySelector('canvas'),c.upper_hex,c.lower_hex,roofHex(c,e.roof));
 if(!inPool){var rb=d.querySelector('.roof');
  [['upper',c.upper_hex],['lower',c.lower_hex],['white','#F2F2F2']].forEach(function(o){var b=document.createElement('button');
   b.style.background=o[1];b.title=o[0];if(e.roof===o[0])b.className='on';
   b.onclick=function(ev){ev.stopPropagation();e.roof=o[0];render()};rb.appendChild(b)});
  var ci=document.createElement('input');ci.type='color';ci.value=/^#/.test(e.roof)?e.roof:roofHex(c,e.roof).toLowerCase();ci.title='any colour';
  ci.onchange=function(){e.roof=ci.value.toUpperCase();render()};ci.onclick=function(ev){ev.stopPropagation()};rb.appendChild(ci)}
 return d}
function render(){var el=document.getElementById('cur'),pl=document.getElementById('pool');el.innerHTML='';pl.innerHTML='';
 document.getElementById('cnt').textContent=cur.length;
 cur.forEach(function(e,i){var d=card(e,i,false);d.draggable=true;
  d.querySelector('.x').onclick=function(){cur.splice(i,1);render()};
  d.ondragstart=function(){drag=i};d.ondragover=function(ev){ev.preventDefault();d.classList.add('over')};
  d.ondragleave=function(){d.classList.remove('over')};
  d.ondrop=function(ev){ev.preventDefault();var mv=cur.splice(drag,1)[0];cur.splice(i,0,mv);render()};el.appendChild(d)});
 var used=cur.map(function(e){return e.code});
 Object.keys(ALL).filter(function(k){return used.indexOf(k)<0}).forEach(function(k){var e={code:k,roof:'upper'},d=card(e,0,true);
  d.onclick=function(){cur.push(e);render()};pl.appendChild(d)})}
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
    cur = [{"code": p["combo"], "roof": p.get("roof", "upper")} for p in paints if isinstance(p, dict) and p.get("combo") in allc]
    hero = collect_car(car)
    imgs = {"fg": hero["fg"], "mask": hero["hero"]["mask"], "cut": hero["cut"]}

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, body, ctype):
            self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/img/"):
                uri = imgs.get(self.path[5:])
                if uri:
                    self._send(base64.b64decode(uri.split(",", 1)[1]), uri[5:uri.index(";")])
                    return
            page = PAGE.replace("__DATA__", json.dumps(allc)).replace("__CUR__", json.dumps(cur))
            self._send(page.encode(), "text/html; charset=utf-8")

        def do_POST(self):
            if self.path != "/__save" or self.client_address[0] not in ("127.0.0.1", "::1"):
                self.send_error(403); return
            try:
                items = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                assert items and all(e["code"] in allc for e in items), "empty or unknown codes"
                meta = json.loads(car_json.read_text(encoding="utf-8"))
                keep = [p for p in meta["index"]["paints"] if not (isinstance(p, dict) and "combo" in p)]
                meta["index"]["paints"] = keep + [{"combo": e["code"], "roof": e["roof"]} for e in items]
                car_json.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                done = subprocess.run([sys.executable, str(ROOT / "src" / "build_index.py")], cwd=ROOT, capture_output=True, text=True)
                if done.returncode:
                    raise RuntimeError(done.stderr.strip()[-400:])
                cur[:] = items
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
