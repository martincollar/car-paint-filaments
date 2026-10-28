"""Review and mark-up tool for the recolor-preview assets of every car.

Usage:  python review_hero.py [--port N]     (binds 127.0.0.1 only; pick an uncommon port)
Open the printed URL. Per car: the neutral photo, its mask and an overlay (keys 1 / 2 / 3), zoom (+ / - / ctrl+wheel,
hold Space to pan, M cycles marks: outline / filled / hidden). Delete a wrong mark: S (select) then click it (or click its dot in W mode), then Delete / Backspace.
Pick a mark type, then either click an area (W: it grows to the connected area of similar colour, adjust the tolerance),
drag a box (B) or drag a loop (L) around it; the marks are saved at once to
cars/<car>/hero_marks.json (polygons in pixels of hero.jpg) and merged by make_hero_assets.py:
  never       must not be repainted          paint       must be repainted (body)     roof   must be repainted (roof)
  neutralise  old paint colour is left here  keep        must keep its colour (e.g. turn-signal lens)
A car's other hero.zones (Doppler's "lower", Torq Summer Pack's "stripe", ...) each get their own button too,
built from that car's zones list, with the zone's own id as the mark type and its own keyboard shortcut.
/calibrate: all cars side by side in the same colours, per-car lightness / contrast sliders, saved as "tone" in hero_assets.json.
"Rebuild" runs make_hero_assets + prepare_hero + build_html for that car, then reloads the images.
The mask is shown as stored: R channel = body paint, G channel = roof paint.
"""
import argparse, json, re, subprocess, sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import config

PAGE = r"""<!doctype html><meta charset="utf-8"><title>Hero review</title>
<style>
*{box-sizing:border-box}body{margin:0;font:13px/1.35 system-ui,sans-serif;background:#1c1c1e;color:#eee;display:flex;flex-direction:column;height:100vh}
header{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;padding:8px 12px;background:#111;border-bottom:1px solid #333}
.grp{display:flex;gap:4px;align-items:center}.grp>span{color:#888;margin-right:2px}
button{font:inherit;color:#eee;background:#2c2c2e;border:1px solid #48484a;border-radius:6px;padding:4px 9px;cursor:pointer}
button:hover{background:#3a3a3c}button.on{background:#0a84ff;border-color:#0a84ff}
button.t{border-width:2px}button.t.on{color:#000;font-weight:600}
#main{flex:1;display:flex;min-height:0}
#vp{flex:1;overflow:auto;background:#3a3a3c;position:relative}
#stage{position:relative;background:#fff;margin:0}
#stage img{position:absolute;left:0;top:0;width:100%;height:100%;display:block;user-select:none;-webkit-user-drag:none}
#cv{position:absolute;left:0;top:0;cursor:crosshair;touch-action:none}
#side{width:300px;overflow:auto;background:#161618;border-left:1px solid #333;padding:8px}
.m{display:grid;grid-template-columns:14px 1fr auto;gap:2px 6px;align-items:center;padding:5px;border-radius:6px;border:1px solid transparent}
.m.sel{border-color:#fff;background:#232326}.m i{width:12px;height:12px;border-radius:50%}
.m input{grid-column:1/4;background:#0c0c0d;border:1px solid #333;border-radius:4px;color:#eee;padding:2px 5px;font:inherit}
#st{color:#8e8e93}#log{white-space:pre-wrap;font:11px/1.3 ui-monospace,monospace;color:#aaa;margin-top:8px}
</style>
<header>
 <div class="grp" id="cars"></div>
 <div class="grp"><a href="/calibrate" style="color:#7cf">light calibration →</a></div>
 <div class="grp"><span>view</span><button data-v="photo">1 photo</button><button data-v="mask">2 mask</button><button data-v="ov">3 overlay</button></div>
 <div class="grp"><span>zoom</span><button id="zo">−</button><button id="zf">fit</button><button id="z1">100%</button><button id="zi">+</button></div>
 <div class="grp"><span>shape</span><button data-s="wand">W click-select</button><button data-s="rect">B box</button><button data-s="loop">L loop</button><button data-s="sel">S select / delete</button><span>tolerance</span><input type="range" id="tol" min="5" max="90" value="30"><b id="tolv">30</b></div>
 <div class="grp" id="tools"><span>mark</span></div>
 <div class="grp"><span>marks</span><button id="mm">M outline</button></div>
 <div class="grp"><button id="undo">undo</button><button id="rebuild">rebuild this car</button><span id="st"></span></div>
</header>
<div id="main"><div id="vp"><div id="stage"><img id="ph"><img id="mk"><canvas id="cv"></canvas></div></div>
<div id="side"><b>Marks</b> <span id="cnt"></span><div id="list"></div><div id="log"></div></div></div>
<script>
var CARS=__CARS__;
var USED_KEYS=['W','B','L','S']; // shape-tool shortcuts; mark-tool keys must not collide
var ZONE_PALETTE=['#ff2d55','#5e5ce6','#ffd60a','#bf5af2','#ff9f0a','#30d158'];
function toolsFor(c){
 var t=[['never','N','#ff3b30','must NOT be repainted'],['paint','P','#34c759','must be repainted (body)']],used=USED_KEYS.concat(['N','P','R','O','K']);
 var zones=c.zones||[],roofZone=zones.filter(function(z){return (z.channels||[]).indexOf(1)>=0})[0];
 // a modern zone can reuse channel 1 under its own id (e.g. an "interior" zone on a car with no roof); only the
 // legacy id "roof" (or no zone at all there) keeps the mark type "roof"
 var ch1Type=(roofZone&&roofZone.id!=='roof')?roofZone.id:'roof';
 t.push([ch1Type,'R','#00c7be','must be repainted ('+(roofZone?roofZone.label.toLowerCase():'roof')+')']);
 // extra zones: anything not on channel 0 (body, already "paint") or channel 1 (already "roof")
 zones.filter(function(z){var ch=z.channels||[];return ch.indexOf(0)<0&&ch.indexOf(1)<0}).forEach(function(z,i){
  var key=null;for(var j=0;j<z.id.length;j++){var c2=z.id[j].toUpperCase();if(c2>='A'&&c2<='Z'&&used.indexOf(c2)<0){key=c2;break}}
  if(!key)for(var n=1;n<10;n++)if(used.indexOf(''+n)<0){key=''+n;break}
  used.push(key);t.push([z.id,key,ZONE_PALETTE[i%ZONE_PALETTE.length],'must be repainted ('+z.label.toLowerCase()+')'])});
 t.push(['neutralise','O','#ff9500','old colour left here']);
 t.push(['keep','K','#0a84ff','keep its colour']);
 return t}
var TOOLS=toolsFor(CARS[0]);
var keepView=false, shape='wand', tol=30, orig=null, car=CARS[0], marks=[], mmode='outline', view='ov', zoom=1, nw=1, nh=1, tool='never', cur=null, sel=-1, panning=false, T=Date.now(), saveT=null;
var $=function(i){return document.getElementById(i)}, cv=$('cv'), ctx=cv.getContext('2d'), vp=$('vp'), stage=$('stage');
function status(t){$('st').textContent=t}
CARS.forEach(function(c){var b=document.createElement('button');b.textContent=c.display;b.dataset.car=c.name;b.onclick=function(){load(c)};$('cars').appendChild(b)});
function renderTools(){$('tools').querySelectorAll('button').forEach(function(b){b.remove()});
 TOOLS.forEach(function(t){var b=document.createElement('button');b.className='t';b.textContent=t[1]+' '+t[3];b.dataset.t=t[0];b.style.borderColor=t[2];
  b.onclick=function(){tool=t[0];tools()};$('tools').appendChild(b)});
 if(!TOOLS.filter(function(t){return t[0]===tool})[0])tool='never';
 tools()}
renderTools();
function tools(){document.querySelectorAll('#tools button').forEach(function(b){var t=TOOLS.filter(function(x){return x[0]===b.dataset.t})[0];
 b.classList.toggle('on',b.dataset.t===tool);b.style.background=b.dataset.t===tool?t[2]:''})}
function shapes(){cv.style.cursor=shape==='sel'?'pointer':'crosshair';document.querySelectorAll('[data-s]').forEach(function(b){b.classList.toggle('on',b.dataset.s===shape)})}
document.querySelectorAll('[data-s]').forEach(function(b){b.onclick=function(){shape=b.dataset.s;shapes()}});
$('tol').oninput=function(){tol=+this.value;$('tolv').textContent=tol};
function views(){document.querySelectorAll('[data-v]').forEach(function(b){b.classList.toggle('on',b.dataset.v===view)});
 $('ph').style.display=view==='mask'?'none':'block';$('mk').style.display=view==='photo'?'none':'block';
 $('mk').style.mixBlendMode=view==='ov'?'screen':'normal';$('mk').style.opacity=view==='ov'?.85:1;stage.style.background=view==='mask'?'#000':'#fff'}
document.querySelectorAll('[data-v]').forEach(function(b){b.onclick=function(){view=b.dataset.v;views()}});
function wand(x,y,t){x=Math.round(x);y=Math.round(y);if(!orig||x<0||y<0||x>=nw||y>=nh)return null;
 var d=orig.data,W=nw,H=nh,reg=new Uint8Array(W*H),vis=new Uint8Array(W*H),i0=(y*W+x)*4,r0=d[i0],g0=d[i0+1],b0=d[i0+2],t2=t*t,st=[y*W+x];vis[y*W+x]=1;reg[y*W+x]=1;
 function ok(p){var i=p*4,a=d[i]-r0,b=d[i+1]-g0,c=d[i+2]-b0;return a*a+b*b+c*c<=t2}
 while(st.length){var p=st.pop(),px=p%W,py=(p-px)/W,n=[px>0?p-1:-1,px<W-1?p+1:-1,py>0?p-W:-1,py<H-1?p+W:-1];
  for(var k=0;k<4;k++){var q=n[k];if(q>=0&&!vis[q]){vis[q]=1;if(ok(q)){reg[q]=1;st.push(q)}}}}
 return reg}
function regionCanvas(m){var reg=wand(m.seed[0],m.seed[1],m.tol);if(!reg)return null;var c=document.createElement('canvas');c.width=nw;c.height=nh;
 var x=c.getContext('2d'),id=x.createImageData(nw,nh),hx=color(m.type),r=parseInt(hx.substr(1,2),16),g=parseInt(hx.substr(3,2),16),b=parseInt(hx.substr(5,2),16);
 for(var i=0;i<reg.length;i++)if(reg[i]){id.data[4*i]=r;id.data[4*i+1]=g;id.data[4*i+2]=b;id.data[4*i+3]=255}x.putImageData(id,0,0);return c}
function regions(){marks.forEach(function(m){if(m.shape==='wand'&&!m._cv)m._cv=regionCanvas(m)});draw()}
function inPoly(p,pts){var c=false;for(var i=0,j=pts.length-1;i<pts.length;j=i++){var a=pts[i],b=pts[j];if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])c=!c}return c}
function hit(p){for(var i=marks.length-1;i>=0;i--){var m=marks[i];
  if(m.shape==='wand'){if(Math.hypot(p[0]-m.seed[0],p[1]-m.seed[1])*zoom<9)return i;
   if(m._cv&&m._cv.getContext('2d').getImageData(Math.round(p[0]),Math.round(p[1]),1,1).data[3]>0)return i}
  else if(inPoly(p,m.points))return i}return -1}
function select(i){sel=i;list();draw();var e=document.querySelector('#list .sel');if(e)e.scrollIntoView({block:'nearest'})}
function removeSel(){if(sel<0)return;marks.splice(sel,1);sel=-1;save();list();draw()}
function color(t){var m=TOOLS.filter(function(x){return x[0]===t})[0];return m?m[2]:'#8e8e93'}
function load(c){car=c;document.querySelectorAll('#cars button').forEach(function(b){b.classList.toggle('on',b.dataset.car===c.name)});
 TOOLS=toolsFor(c);renderTools();
 marks=[];sel=-1;T=Date.now();$('ph').src=c.name+'/'+c.photo+'?t='+T;$('mk').src=c.name+'/'+c.mask+'?t='+T;
 orig=null;var oi=new Image();oi.onload=function(){var c=document.createElement('canvas');c.width=oi.naturalWidth;c.height=oi.naturalHeight;c.getContext('2d').drawImage(oi,0,0);orig=c.getContext('2d').getImageData(0,0,c.width,c.height);regions()};oi.src=c.name+'/sources/hero.jpg?t='+T;
 $('ph').onload=function(){nw=this.naturalWidth;nh=this.naturalHeight;if(keepView)keepView=false;else fit()};
 fetch(c.name+'/hero_marks.json?t='+T).then(function(r){return r.ok?r.json():{marks:[]}}).then(function(j){marks=j.marks||[];list();regions()});status('')}
function setZoom(z,ax,ay){var old=zoom;zoom=Math.max(.05,Math.min(8,z));stage.style.width=nw*zoom+'px';stage.style.height=nh*zoom+'px';
 cv.width=nw*zoom;cv.height=nh*zoom;cv.style.width=cv.width+'px';cv.style.height=cv.height+'px';
 if(ax!=null){vp.scrollLeft=(vp.scrollLeft+ax)*zoom/old-ax;vp.scrollTop=(vp.scrollTop+ay)*zoom/old-ay}draw()}
function fit(){if(vp.clientWidth<50||vp.clientHeight<50){setTimeout(fit,60);return}setZoom(Math.min(vp.clientWidth/nw,vp.clientHeight/nh)*.98)}
$('zf').onclick=fit;$('z1').onclick=function(){setZoom(1)};$('zi').onclick=function(){setZoom(zoom*1.4,vp.clientWidth/2,vp.clientHeight/2)};
$('zo').onclick=function(){setZoom(zoom/1.4,vp.clientWidth/2,vp.clientHeight/2)};
vp.addEventListener('wheel',function(e){if(e.ctrlKey||e.metaKey){e.preventDefault();var r=vp.getBoundingClientRect();setZoom(zoom*(e.deltaY<0?1.15:1/1.15),e.clientX-r.left,e.clientY-r.top)}},{passive:false});
function path(p,close){ctx.beginPath();p.forEach(function(q,i){i?ctx.lineTo(q[0]*zoom,q[1]*zoom):ctx.moveTo(q[0]*zoom,q[1]*zoom)});if(close)ctx.closePath()}
function draw(){ctx.clearRect(0,0,cv.width,cv.height);if(mmode!=='hidden')marks.forEach(function(m,i){var c=color(m.type);
 if(m.shape==='wand'){if(m._cv){ctx.globalAlpha=mmode==='fill'?(i===sel?.55:.4):(i===sel?.4:.22);ctx.drawImage(m._cv,0,0,nw*zoom,nh*zoom);ctx.globalAlpha=1}
  if(m.seed){ctx.beginPath();ctx.arc(m.seed[0]*zoom,m.seed[1]*zoom,4,0,6.3);ctx.fillStyle='#fff';ctx.fill();ctx.lineWidth=2;ctx.strokeStyle=c;ctx.stroke()}return}
 path(m.points,true);
 if(mmode==='fill'||i===sel){ctx.fillStyle=c+(mmode==='fill'?(i===sel?'66':'33'):'22');ctx.fill()}
 ctx.lineWidth=i===sel?2.5:1.2;ctx.strokeStyle=c;ctx.stroke()});
 if(cur){ctx.lineWidth=2;ctx.strokeStyle=color(tool);if(shape==='rect'&&cur.length===2){var a=cur[0],b=cur[1];ctx.strokeRect(a[0]*zoom,a[1]*zoom,(b[0]-a[0])*zoom,(b[1]-a[1])*zoom)}else{path(cur,false);ctx.stroke()}}}
function pt(e){var r=cv.getBoundingClientRect();return[(e.clientX-r.left)/zoom,(e.clientY-r.top)/zoom]}
cv.addEventListener('pointerdown',function(e){if(e.button!==0)return;cv.setPointerCapture(e.pointerId);
 if(panning){cv._pan=[e.clientX,e.clientY,vp.scrollLeft,vp.scrollTop];return}
 if(shape==='sel'){select(hit(pt(e)));return}
 if(shape==='wand'){var p=pt(e);var near=-1;marks.forEach(function(m,i){if(m.shape==='wand'&&Math.hypot(p[0]-m.seed[0],p[1]-m.seed[1])*zoom<9)near=i});if(near>=0){select(near);return}var m={type:tool,shape:'wand',seed:[Math.round(p[0]),Math.round(p[1])],tol:tol,note:''};m._cv=regionCanvas(m);marks.push(m);sel=marks.length-1;save();list();draw();return}
 cur=[pt(e)]});
cv.addEventListener('pointermove',function(e){if(cv._pan){vp.scrollLeft=cv._pan[2]-(e.clientX-cv._pan[0]);vp.scrollTop=cv._pan[3]-(e.clientY-cv._pan[1]);return}
 if(!cur)return;var p=pt(e),l=cur[cur.length-1];if(shape==='rect'){cur=[cur[0],p];draw();return}if(Math.hypot(p[0]-l[0],p[1]-l[1])*zoom>3){cur.push(p);draw()}});
cv.addEventListener('pointerup',function(){if(cv._pan){cv._pan=null;return}
 if(cur&&shape==='rect'&&cur.length===2&&Math.abs(cur[1][0]-cur[0][0])*zoom>4&&Math.abs(cur[1][1]-cur[0][1])*zoom>4){var a=cur[0],b=cur[1];marks.push({type:tool,note:'',points:[[a[0],a[1]],[b[0],a[1]],[b[0],b[1]],[a[0],b[1]]].map(function(q){return[Math.round(q[0]*10)/10,Math.round(q[1]*10)/10]})});sel=marks.length-1;save()}
 else if(cur&&shape!=='rect'&&cur.length>=3){marks.push({type:tool,note:'',points:cur.map(function(p){return[Math.round(p[0]*10)/10,Math.round(p[1]*10)/10]})});sel=marks.length-1;save()}
 cur=null;list();draw()});
function list(){var l=$('list');l.innerHTML='';$('cnt').textContent=marks.length?'('+marks.length+')':'';
 marks.forEach(function(m,i){var d=document.createElement('div');d.className='m'+(i===sel?' sel':'');
  d.innerHTML='<i style="background:'+color(m.type)+'"></i><span>'+m.type+' · '+(m.shape==='wand'?'click ('+m.seed[0]+','+m.seed[1]+') tol '+m.tol:m.points.length+' pts')+'</span><button>✕</button>'+(m.shape==='wand'?'<input class="tl" type="range" min="5" max="90">':'')+'<input class="nt" placeholder="note (optional)">';
  var nt=d.querySelector('.nt');nt.value=m.note||'';nt.onchange=function(){m.note=this.value;save()};
  var tl=d.querySelector('.tl');if(tl){tl.value=m.tol;tl.onclick=function(ev){ev.stopPropagation()};tl.onchange=function(){m.tol=+this.value;m._cv=null;regions();save();list()}};
  d.querySelector('button').onclick=function(ev){ev.stopPropagation();marks.splice(i,1);sel=-1;save();list();draw()};
  d.onclick=function(){sel=i;list();draw()};l.appendChild(d)});var se=l.querySelector('.sel');if(se)se.scrollIntoView({block:'nearest'})}
function save(){status('saving…');clearTimeout(saveT);saveT=setTimeout(function(){fetch('/api/marks/'+car.name,{method:'POST',body:JSON.stringify({marks:marks},function(k,v){return k==='_cv'?undefined:v})})
 .then(function(r){status(r.ok?'saved '+new Date().toLocaleTimeString():'SAVE FAILED')}).catch(function(){status('SAVE FAILED')})},150)}
function mm(){mmode={outline:'fill',fill:'hidden',hidden:'outline'}[mmode];$('mm').textContent='M '+mmode;draw()}
$('mm').onclick=mm;
$('undo').onclick=function(){marks.pop();sel=-1;save();list();draw()};
$('rebuild').onclick=function(){status('rebuilding…');$('log').textContent='';fetch('/api/rebuild/'+car.name,{method:'POST'}).then(function(r){return r.json()}).then(function(j){
 $('log').textContent=j.log;status(j.ok?'rebuilt '+new Date().toLocaleTimeString():'REBUILD FAILED');T=Date.now();keepView=true;
 $('ph').src=car.name+'/'+car.photo+'?t='+T;$('mk').src=car.name+'/'+car.mask+'?t='+T})};
document.addEventListener('keydown',function(e){if(e.target.tagName==='INPUT')return;var k=e.key.toLowerCase();
 if(k===' '){panning=true;cv.style.cursor='grab';e.preventDefault()}
 else if((e.ctrlKey||e.metaKey)&&k==='z'){$('undo').click();e.preventDefault()}
 else if(k==='1'||k==='2'||k==='3'){view=['photo','mask','ov'][+k-1];views()}
 else if(k==='+'||k==='=')$('zi').click();else if(k==='-')$('zo').click();else if(k==='0')fit();
 else if(k==='m')mm();else if(k==='s'){shape='sel';shapes()}else if(k==='delete'||k==='backspace'){removeSel();e.preventDefault()}else if(k==='w'){shape='wand';shapes()}else if(k==='b'){shape='rect';shapes()}else if(k==='l'){shape='loop';shapes()}else if(k==='escape'){cur=null;sel=-1;list();draw()}
 else TOOLS.forEach(function(t){if(t[1].toLowerCase()===k){tool=t[0];tools()}})});
document.addEventListener('keyup',function(e){if(e.key===' '){panning=false;cv.style.cursor='crosshair'}});
tools();shapes();views();load(CARS[0]);
</script>"""

CAL = r"""<!doctype html><meta charset="utf-8"><title>Light calibration</title>
<style>
*{box-sizing:border-box}body{margin:0;font:13px/1.35 system-ui,sans-serif;background:#1c1c1e;color:#eee}
#top{position:sticky;top:0;z-index:5;background:#111;border-bottom:1px solid #333;box-shadow:0 4px 14px #0008}
header{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;padding:8px 12px}
#ctl{display:grid;gap:6px;padding:0 8px 8px;grid-template-columns:repeat(__N__,1fr)}
a{color:#7cf}input[type=text]{background:#0c0c0d;border:1px solid #444;border-radius:5px;color:#eee;padding:4px 7px;font:inherit;width:330px}
button{font:inherit;color:#eee;background:#2c2c2e;border:1px solid #48484a;border-radius:6px;padding:4px 10px;cursor:pointer}button:hover{background:#3a3a3c}
button.go{background:#0a84ff;border-color:#0a84ff}#st{color:#8e8e93}
#grid{display:grid;gap:6px;padding:8px;grid-template-columns:repeat(__N__,1fr)}
.ctl h3{margin:0 0 4px;font-size:14px}.cbox{background:#1c1c1e;border-radius:6px;padding:6px 8px}.ctl{display:grid;grid-template-columns:78px 1fr 46px;gap:2px 6px;align-items:center;margin-bottom:3px;color:#aaa}
.col canvas{width:100%;background:#fff;display:block;margin-top:6px;border-radius:4px}
#log{white-space:pre-wrap;font:11px/1.3 ui-monospace,monospace;color:#aaa;padding:0 12px 12px}
</style>
<div id="top"><header><b>Light calibration</b><a href="/">← review / mark-up</a>
<span>colours <input type="text" id="cols" value="#F2F2F2, #D9B26A, #B5473A, #2F5FA8, #151515"></span>
<button id="go" class="go">save &amp; rebuild all cars</button><span id="st"></span></header><div id="ctl"></div></div>
<div id="grid"></div><div id="log"></div>
<script>
var CARS=__CARS__, W=520, $=function(i){return document.getElementById(i)};
var M=[[0.4124564,0.3575761,0.1804375],[0.2126729,0.7151522,0.0721750],[0.0193339,0.1191920,0.9503041]];
var Mi=[[3.2404542,-1.5371385,-0.4985314],[-0.9692660,1.8760108,0.0415560],[0.0556434,-0.2040259,1.0572252]],WP=[0.95047,1,1.08883];
function lin(c){c/=255;return c>0.04045?Math.pow((c+0.055)/1.055,2.4):c/12.92}
function gam(c){c=c<=0.0031308?12.92*c:1.055*Math.pow(c,1/2.4)-0.055;return Math.max(0,Math.min(1,c))*255}
function f(t){return t>216/24389?Math.cbrt(t):(24389/27*t+16)/116}
function finv(t){var t3=t*t*t;return t3>216/24389?t3:(116*t-16)/(24389/27)}
function toLab(r,g,b){r=lin(r);g=lin(g);b=lin(b);var fx=f((M[0][0]*r+M[0][1]*g+M[0][2]*b)/WP[0]),fy=f(M[1][0]*r+M[1][1]*g+M[1][2]*b),fz=f((M[2][0]*r+M[2][1]*g+M[2][2]*b)/WP[2]);return[116*fy-16,500*(fx-fy),200*(fy-fz)]}
function hexRgb(h){return[1,3,5].map(function(i){return parseInt(h.substr(i,2),16)})}
function px(img,w,h){var c=document.createElement('canvas');c.width=w;c.height=h;var x=c.getContext('2d');x.drawImage(img,0,0,w,h);return x.getImageData(0,0,w,h)}
function load(src){return new Promise(function(res){var i=new Image();i.onload=function(){res(i)};i.src=src+'?t='+Date.now()})}
// same maths as HERO_JS in build_html.py (lightness shading around the body mean, contrast cap, per-car tone)
function prep(c){return Promise.all([load(c.name+'/sources/hero_neutral.jpg'),load(c.name+'/sources/hero_mask.png')]).then(function(r){
 var h=Math.round(r[0].naturalHeight*W/r[0].naturalWidth);c.h=h;c.base=px(r[0],W,h);c.mk=px(r[1],W,h).data;var n=W*h,d=c.base.data;c.L=new Float32Array(n*3);var sum=[0,0],wt=[0,0];
 for(var i=0;i<n;i++){var l=toLab(d[4*i],d[4*i+1],d[4*i+2]);c.L[3*i]=l[0];c.L[3*i+1]=l[1];c.L[3*i+2]=l[2];for(var k=0;k<2;k++){var a=c.mk[4*i+k]/255;sum[k]+=a*l[0];wt[k]+=a}}
 c.Lm=[sum[0]/wt[0],sum[1]/wt[1]];var vr=[0,0];for(var j=0;j<n;j++)for(var q=0;q<2;q++){var aq=c.mk[4*j+q]/255,dq=c.L[3*j]-c.Lm[q];vr[q]+=aq*dq*dq}
 c.Sc=[0,1].map(function(q){return wt[q]>0?Math.min(1,12/Math.sqrt(vr[q]/wt[q])):1});c.ready=true})}
function render(c,hex,cv){cv.width=W;cv.height=c.h;var ctx=cv.getContext('2d'),tb=toLab.apply(null,hexRgb(hex)),tr=c.roof?toLab.apply(null,hexRgb(c.roof)):tb,
 out=ctx.createImageData(W,c.h),o=out.data,d=c.base.data,n=W*c.h,DL=c.dl,CS=c.contrast;
 for(var i=0;i<n;i++){var ab=c.mk[4*i]/255,ar=c.mk[4*i+1]/255,r=d[4*i],g=d[4*i+1],b=d[4*i+2];
  if(ab>0||ar>0){var kk=ab>=ar?0:1,t=kk?tr:tb,a=kk?ar:ab,t0=Math.max(0,Math.min(100,t[0]+DL)),dev=(c.L[3*i]-c.Lm[kk])*c.Sc[kk]*CS;
   dev*=dev>0?Math.min(1,(100-t0)/(100-c.Lm[kk])):Math.min(1,t0/c.Lm[kk]);
   var ly=(Math.max(0,Math.min(100,t0+dev))+16)/116,fx=ly+t[1]/500,fz=ly-t[2]/200,X=finv(fx)*WP[0],Y=finv(ly),Z=finv(fz)*WP[2];
   r=r*(1-a)+gam(Mi[0][0]*X+Mi[0][1]*Y+Mi[0][2]*Z)*a;g=g*(1-a)+gam(Mi[1][0]*X+Mi[1][1]*Y+Mi[1][2]*Z)*a;b=b*(1-a)+gam(Mi[2][0]*X+Mi[2][1]*Y+Mi[2][2]*Z)*a}
  o[4*i]=r;o[4*i+1]=g;o[4*i+2]=b;o[4*i+3]=255}ctx.putImageData(out,0,0)}
var grid=$('grid'),cells=[],pending=false;
function colours(){return $('cols').value.split(/[ ,;]+/).filter(function(x){return /^#[0-9a-f]{6}$/i.test(x)})}
function build(){grid.innerHTML='';$('ctl').innerHTML='';cells=[];CARS.forEach(function(c){var col=document.createElement('div');col.className='col';col.innerHTML='<div class="cv"></div>';
 var box=document.createElement('div');box.className='cbox';
 box.innerHTML='<h3>'+c.display+'</h3><div class="ctl"><span>lightness</span><input type="range" min="-30" max="30" step="0.5"><b></b></div><div class="ctl"><span>contrast</span><input type="range" min="0.3" max="1.8" step="0.05"><b></b></div><button>reset</button>';
 var sl=box.querySelectorAll('input'),bs=box.querySelectorAll('b');
 function sync(){sl[0].value=c.dl;sl[1].value=c.contrast;bs[0].textContent=(c.dl>0?'+':'')+c.dl;bs[1].textContent='\u00d7'+c.contrast.toFixed(2)}
 sl[0].oninput=function(){c.dl=+this.value;sync();redraw()};sl[1].oninput=function(){c.contrast=+this.value;sync();redraw()};
 box.querySelector('button').onclick=function(){c.dl=0;c.contrast=1;sync();redraw()};sync();c.cvs=[];grid.appendChild(col);$('ctl').appendChild(box)});rows()}
function rows(){CARS.forEach(function(c,i){var holder=grid.children[i].querySelector('.cv');holder.innerHTML='';c.cvs=colours().map(function(){var cv=document.createElement('canvas');holder.appendChild(cv);return cv})});redraw()}
function redraw(){if(pending)return;pending=true;requestAnimationFrame(function(){pending=false;var cs=colours();CARS.forEach(function(c){if(c.ready)c.cvs.forEach(function(cv,j){render(c,cs[j],cv)})})})}
$('cols').onchange=rows;
$('go').onclick=function(){$('st').textContent='saving & rebuilding…';var t={};CARS.forEach(function(c){t[c.name]={dl:c.dl,contrast:Math.round(c.contrast*100)/100}});
 fetch('/api/tone',{method:'POST',body:JSON.stringify({tones:t})}).then(function(r){return r.json()}).then(function(j){$('log').textContent=j.log;$('st').textContent=j.ok?'saved & rebuilt '+new Date().toLocaleTimeString():'FAILED'})};
build();Promise.all(CARS.map(prep)).then(redraw);
</script>"""

STEPS = ("make_hero_assets.py", "prepare_hero.py", "build_html.py")

def _hero_cars():
    for d in sorted(p for p in config.CARS_DIR.iterdir() if (p / "car.json").exists()):
        meta = json.loads((d / "car.json").read_text(encoding="utf-8"))
        if meta.get("hero"):
            yield d.name, meta

class Handler(SimpleHTTPRequestHandler):
    """Serves cars/ plus a tiny API: POST /api/marks/<car> saves hero_marks.json, POST /api/rebuild/<car> rebuilds."""
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/calibrate":
            cars = []
            for name, meta in _hero_cars():
                a = config.car_dir(name) / "hero_assets.json"
                tone = (json.loads(a.read_text(encoding="utf-8")).get("tone") if a.exists() else None) or {}
                cars.append({"name": name, "display": meta.get("display", name), "roof": meta["hero"].get("roof"),
                             "dl": tone.get("dl", 0), "contrast": tone.get("contrast", 1)})
            body = CAL.replace("__CARS__", json.dumps(cars)).replace("__N__", str(len(cars))).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path in ("/", "/index.html"):
            cars = []
            for d in sorted(p for p in config.CARS_DIR.iterdir() if (p / "car.json").exists()):
                meta = json.loads((d / "car.json").read_text(encoding="utf-8"))
                if meta.get("hero"):
                    cars.append({"name": d.name, "display": meta.get("display", d.name),
                                 "photo": meta["hero"]["photo"], "mask": meta["hero"]["mask"],
                                 "zones": meta["hero"].get("zones") or []})
            body = PAGE.replace("__CARS__", json.dumps(cars)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/tone":
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            log, ok = [], True
            for car, tone in data.get("tones", {}).items():
                if not (config.CARS_DIR / car / "hero_assets.json").exists():
                    continue
                path = config.CARS_DIR / car / "hero_assets.json"
                cfg = json.loads(path.read_text(encoding="utf-8"))
                cfg["tone"] = {"dl": float(tone["dl"]), "contrast": float(tone["contrast"])}
                path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
                for step in ("prepare_hero.py", "build_html.py"):
                    r = subprocess.run([sys.executable, str(Path(__file__).parent / step), "--car", car], capture_output=True, text=True)
                    log.append(f"$ {step} --car {car}\n{(r.stdout + r.stderr).strip()}")
                    ok = ok and r.returncode == 0
                print(f"saved tone {cfg['tone']} for {car}", flush=True)
            return self._json({"ok": ok, "log": "\n".join(log)})
        m = re.fullmatch(r"/api/(marks|rebuild)/([a-z0-9_-]+)", self.path)
        if not m or not (config.CARS_DIR / m.group(2) / "car.json").exists():
            return self._json({"ok": False, "log": "unknown car or endpoint"}, 404)
        action, car = m.groups()
        if action == "marks":
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            (config.CARS_DIR / car / "hero_marks.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
            print(f"saved {len(data.get('marks', []))} marks for {car}", flush=True)
            return self._json({"ok": True})
        log, ok = [], True
        for step in STEPS:
            r = subprocess.run([sys.executable, str(Path(__file__).parent / step), "--car", car], capture_output=True, text=True)
            log.append(f"$ {step} --car {car}\n{(r.stdout + r.stderr).strip()}")
            if r.returncode:
                ok = False
                break
        self._json({"ok": ok, "log": "\n".join(log)})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=53117)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(config.CARS_DIR)))
    print(f"hero review: http://localhost:{args.port}/   (Ctrl-C to stop)")
    srv.serve_forever()

if __name__ == "__main__":
    main()
