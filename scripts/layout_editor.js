/* Layout editor for the root page tiles and the detail-page header card (`.head-card`, saved to headcard-*.css). Only loaded by `?edit` on the preview server (scripts/serve_preview.py).
   - drag an element, or select it and use the arrow keys (Shift = 10 px)
   - size: + / - keys (Shift = bigger steps), the buttons in the panel, or Alt + mouse wheel
   - rotation: [ and ] keys (Shift = 5 degrees) or the ⟲ ⟳ buttons
   - the panel can be dragged by its title and folded with ▁
   - colours: "Pozadí dlaždice" (tile background) and "Barva textu" (text colour of the selected element)
   - Shift + drag moves the car, Esc deselects
   "Uložit" writes themes/<theme>/tile-offsets.css (or tile-offsets-mobile.css when the window is <= 520 px wide) and
   tile-colors.css, then rebuilds the page. */
(function () {
  var TARGETS = '.tile-name, .tile-tag, .tile-meta, .tile-label, .tile-open, .tile-buy, .head-filters, .tile-deco > *';   // any decoration of a theme's tile.html
  var sel = null, drag = null, touched = {}, colors = {}, lastTile = null;

  var css = document.createElement('style');
  css.textContent =
    '.tile-name a::after{display:none!important}' +
    '.tile-car{display:none!important}' +   // the car link would sit over the decorations and swallow their clicks
    '.tile-deco *{pointer-events:auto!important}' +
    '.le-hover{outline:2px dashed #2563eb;outline-offset:3px;cursor:move}' +
    '.le-sel{outline:2px solid #e11d48!important;outline-offset:3px;cursor:move}' +
    '#le-panel{position:fixed;z-index:99999;right:8px;top:8px;width:244px;padding:10px 12px;border-radius:10px;background:#111;color:#fff;' +
    'font:12px/1.4 -apple-system,Segoe UI,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.4)}' +
    '#le-panel b{display:block;margin-bottom:6px;font-size:13px}#le-panel button{margin:6px 4px 0 0;padding:4px 9px;border:0;border-radius:6px;' +
    'background:#2563eb;color:#fff;font:inherit;cursor:pointer}#le-panel button.g{background:#444}#le-panel .m{color:#9ca3af;margin-top:6px}' +
    '#le-panel label{display:flex;align-items:center;justify-content:space-between;margin-top:8px}#le-panel input[type=color]{width:42px;height:24px;padding:0;border:0;background:none}';
  document.head.appendChild(css);

  var panel = document.createElement('div');
  panel.id = 'le-panel';
  panel.innerHTML = '<b id="le-head" style="cursor:move;display:flex;justify-content:space-between;user-select:none">Layout editor' +
    '<span id="le-min" style="cursor:pointer;padding:0 4px" title="sbalit">▁</span></b><div id="le-body"><div id="le-info"></div>' +
    '<div><button class="g" id="le-minus">−</button><button class="g" id="le-plus">+</button>' +
    '<button class="g" id="le-rl" title="otočit doleva">⟲</button><button class="g" id="le-rr" title="otočit doprava">⟳</button>' +
    '<button class="g" id="le-reset">Vrátit prvek</button></div>' +
    '<label>Pozadí dlaždice <input type="color" id="le-bg"></label>' +
    '<label>Barva textu prvku <input type="color" id="le-fg"></label>' +
    '<button id="le-save">Uložit</button>' +
    '<div class="m">Táhni / šipky = posun · + − nebo Alt+kolečko = velikost · [ ] = otočení · Shift+tah = auto</div>' +
    '<div class="m" id="le-msg">Šířka okna: ' + innerWidth + ' px → posuny a velikosti se ukládají ' + (innerWidth <= 520 ? 'jen pro mobil' : 'pro všechny šířky') + '.</div></div>';
  document.body.appendChild(panel);
  var info = panel.querySelector('#le-info'), msg = panel.querySelector('#le-msg'),
      bg = panel.querySelector('#le-bg'), fg = panel.querySelector('#le-fg');

  function offset(el) {
    var m = /(-?[\d.]+)px\s+(-?[\d.]+)px/.exec(getComputedStyle(el).translate || '');
    return m ? [parseFloat(m[1]), parseFloat(m[2])] : [0, 0];
  }
  function scaleOf(el) { var v = parseFloat(getComputedStyle(el).scale); return isNaN(v) ? 1 : v; }
  function rotOf(el) { var v = parseFloat(getComputedStyle(el).rotate); return isNaN(v) ? 0 : v; }
  function theme(el) { var t = el.closest('.tile'); return t && (/tile--([\w-]+)/.exec(t.className) || [])[1]; }
  function key(el) {
    var cls = Array.prototype.filter.call(el.classList, function (c) { return /^(tile-|t-|head-)/.test(c) && !/^le-/.test(c); })
      .sort(function (a, b) { return b.length - a.length; })[0];
    return '.tile--' + theme(el) + (el.closest('.head-card') ? '.head-card' : '') + ' .' + cls;
  }
  function hex(c) {
    var m = /(\d+)[, ]+(\d+)[, ]+(\d+)/.exec(c || '');
    return m ? '#' + [1, 2, 3].map(function (i) { return ('0' + (+m[i]).toString(16)).slice(-2); }).join('') : '#000000';
  }
  function origin(el) { return el.matches('.t-star, .t-shield, .tile-stage') || rotOf(el) !== 0 ? 'center' : 'left center'; }
  function setRot(el, deg) {
    deg = Math.round(deg * 10) / 10; el.style.rotate = deg + 'deg'; el.style.transformOrigin = origin(el);
    touched[key(el)] = el; show();
  }
  function setPos(el, x, y) { el.style.translate = x + 'px ' + y + 'px'; touched[key(el)] = el; show(); }
  function setScale(el, s) {
    s = Math.max(0.2, Math.min(4, Math.round(s * 100) / 100));
    el.style.scale = s; el.style.transformOrigin = origin(el); touched[key(el)] = el; show();
  }
  function show() {
    if (!sel) { info.textContent = 'Klikni na prvek v dlaždici.'; return; }
    var o = offset(sel);
    info.innerHTML = '<b style="margin:0">' + key(sel).split(' ')[1] + '</b>posun ' + o[0] + ', ' + o[1] + ' px · velikost ' + Math.round(scaleOf(sel) * 100) + ' % · otočení ' + rotOf(sel) + '°';
    fg.value = hex(getComputedStyle(sel).color);
  }
  function pick(e) {
    var tile = e.target.closest && e.target.closest('.tile');
    if (!tile) return null;
    if (e.shiftKey) return tile.querySelector('.tile-stage');
    var t = e.target.closest(TARGETS);
    return t && tile.contains(t) ? t : null;
  }
  function useTile(tile) {
    lastTile = tile;
    bg.value = hex(getComputedStyle(tile.querySelector('.tile-frame')).backgroundColor);
  }

  document.addEventListener('pointerover', function (e) {
    document.querySelectorAll('.le-hover').forEach(function (n) { n.classList.remove('le-hover'); });
    var t = pick(e); if (t && t !== sel) t.classList.add('le-hover');
  });
  document.addEventListener('pointerdown', function (e) {
    if (panel.contains(e.target)) return;
    var tile = e.target.closest && e.target.closest('.tile'); if (tile) useTile(tile);
    var t = pick(e);
    if (sel) sel.classList.remove('le-sel');
    sel = t;
    if (!t) { show(); return; }
    e.preventDefault();
    t.classList.remove('le-hover'); t.classList.add('le-sel');
    var o = offset(t); drag = { x: e.clientX, y: e.clientY, ox: o[0], oy: o[1] };
    show();
  }, true);
  document.addEventListener('pointermove', function (e) {
    if (drag && sel) setPos(sel, Math.round(drag.ox + e.clientX - drag.x), Math.round(drag.oy + e.clientY - drag.y));
  });
  document.addEventListener('pointerup', function () { drag = null; });
  document.addEventListener('click', function (e) { if (!panel.contains(e.target) && pick(e)) e.preventDefault(); }, true);
  document.addEventListener('wheel', function (e) {
    if (sel && e.altKey) { e.preventDefault(); setScale(sel, scaleOf(sel) * (e.deltaY < 0 ? 1.03 : 1 / 1.03)); }
  }, { passive: false });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && sel) { sel.classList.remove('le-sel'); sel = null; show(); return; }
    if (!sel || panel.contains(document.activeElement) && document.activeElement.tagName === 'INPUT') return;
    if (e.key === '+' || e.key === '=' || e.key === '-' || e.key === '_') {
      e.preventDefault();
      var up = e.key === '+' || e.key === '=', f = e.shiftKey ? 1.1 : 1.02;
      setScale(sel, scaleOf(sel) * (up ? f : 1 / f)); return;
    }
    if (e.key === '[' || e.key === ']') { e.preventDefault(); setRot(sel, rotOf(sel) + (e.key === ']' ? 1 : -1) * (e.shiftKey ? 5 : 1)); return; }
    var d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (!d) return;
    e.preventDefault();
    var o = offset(sel), k = e.shiftKey ? 10 : 1;
    setPos(sel, o[0] + d[0] * k, o[1] + d[1] * k);
  });

  panel.querySelector('#le-plus').onclick = function () { if (sel) setScale(sel, scaleOf(sel) * 1.05); };
  panel.querySelector('#le-minus').onclick = function () { if (sel) setScale(sel, scaleOf(sel) / 1.05); };
  panel.querySelector('#le-rl').onclick = function () { if (sel) setRot(sel, rotOf(sel) - 2); };
  panel.querySelector('#le-rr').onclick = function () { if (sel) setRot(sel, rotOf(sel) + 2); };
  panel.querySelector('#le-reset').onclick = function () { if (sel) { setPos(sel, 0, 0); setScale(sel, 1); setRot(sel, 0); } };
  // the panel itself: drag by the title, fold with the button
  var head = panel.querySelector('#le-head'), pd = null;
  head.addEventListener('pointerdown', function (e) {
    if (e.target.id === 'le-min') return;
    var r = panel.getBoundingClientRect(); pd = { x: e.clientX - r.left, y: e.clientY - r.top };
    panel.style.left = r.left + 'px'; panel.style.top = r.top + 'px'; panel.style.right = 'auto'; e.preventDefault();
  });
  document.addEventListener('pointermove', function (e) { if (pd) { panel.style.left = (e.clientX - pd.x) + 'px'; panel.style.top = (e.clientY - pd.y) + 'px'; } });
  document.addEventListener('pointerup', function () { pd = null; });
  panel.querySelector('#le-min').onclick = function () {
    var body = panel.querySelector('#le-body'), hidden = body.style.display === 'none';
    body.style.display = hidden ? '' : 'none'; this.textContent = hidden ? '▁' : '▢'; panel.style.width = hidden ? '244px' : '150px';
  };
  bg.oninput = function () {
    if (!lastTile) { msg.textContent = 'Nejdřív klikni do dlaždice.'; return; }
    var frame = lastTile.querySelector('.tile-frame'), k = '.tile--' + theme(frame) + (lastTile.classList.contains('head-card') ? '.head-card' : '') + ' .tile-frame';
    frame.style.background = bg.value; colors[k + '|background'] = { selector: k, prop: 'background', value: bg.value };
  };
  fg.oninput = function () {
    if (!sel) { msg.textContent = 'Nejdřív vyber prvek.'; return; }
    sel.style.color = fg.value; var k = key(sel); colors[k + '|color'] = { selector: k, prop: 'color', value: fg.value };
  };
  panel.querySelector('#le-save').onclick = function () {
    var themes = {};
    Object.keys(touched).forEach(function (k) {
      var el = touched[k], o = offset(el), t = theme(el);
      (themes[t] = themes[t] || {})[k] = { translate: o[0] + 'px ' + o[1] + 'px', scale: scaleOf(el), rotate: rotOf(el), origin: origin(el) };
    });
    var cols = Object.keys(colors).map(function (k) { return colors[k]; });
    if (!Object.keys(themes).length && !cols.length) { msg.textContent = 'Nic jsi neupravil.'; return; }
    msg.textContent = 'Ukládám…';
    fetch('/__save_offsets', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: innerWidth <= 520 ? 'mobile' : 'all', car: document.body.dataset.car || '', themes: themes, colors: cols }) })
      .then(function (r) { return r.json(); })
      .then(function (r) { msg.textContent = r.ok ? 'Uloženo a přebuilděno.' : 'Chyba: ' + r.error; })
      .catch(function (err) { msg.textContent = 'Chyba: ' + err; });
  };
  show();
})();
