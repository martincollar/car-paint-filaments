"""Calibrate a car's paint colours against photos of real cars.

Card scans age and fade (a Datsun 'blue' chip measured near navy), so each
chip can be checked against photos of the real paint. Per car, the manifest
`cars/<car>/calibration.json` lists the photos:

{
  "photos_dir": "sources/photos",             (gitignored: third-party photos)
  "entries": [
    {"car_code": "903", "year": 1971,          (year optional: matches every year with that code)
     "note": "1971 car, original paint",
     "photos": [
       {"file": "903_blue.jpg", "url": "https://...",
        "bbox": [x0, y0, x1, y1],              (body area in photo pixels, no background)
        "mode": ["hue", 0.52, 0.62, 0.4, 0.15, 1]}    (hue lo, hi, min sat, min v, max v)
        or    ["neutral", 0.2, 0.6]                  (white / silver: max sat, min v)
     ]}
  ]
}

Usage:
    python calibrate_car.py --car <name> [--fetch] [--apply] [--pdf FILE]

  (default)  sample the photos, write data/calibration.json and the
             self-contained report data/calibration_report.html
  --fetch    download photos missing from photos_dir (their `url`)
  --apply    write the suggested colour (mean of the photo medians) as
             `hex` + `hex_note` on the matching swatches of card_layout.json;
             measure_car.py then uses it and keeps the scan value as measured_hex
  --pdf FILE print the report to a PDF with headless Chrome
"""
import argparse, base64, io, json, subprocess, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from PIL import Image
from color_tools import delta_e_2000
import config

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def hsv(a):
    mx, mn = a.max(-1), a.min(-1)
    d = mx - mn
    s = np.where(mx > 0, d / np.where(mx > 0, mx, 1), 0)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    dd = np.where(d > 0, d, 1)
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) / 6
    return np.where(d > 0, h, 0), s, mx


def hexs(c):
    return "#%02X%02X%02X" % tuple(int(round(float(x) * 255)) for x in c)


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def sample(path, bbox, mode):
    """Median / brighter-half colour of the pixels selected by `mode` inside bbox,
    plus a preview image of the selection."""
    a = np.asarray(Image.open(path).convert("RGB")) / 255.0
    x0, y0, x1, y1 = bbox
    st = max(1, (x1 - x0) // 500)
    sub = a[y0:y1:st, x0:x1:st]
    h, s, v = hsv(sub)
    if mode[0] == "hue":
        hh = np.where(h > 0.9, h - 1, h)
        k = (hh >= mode[1]) & (hh <= mode[2]) & (s >= mode[3]) & (v >= mode[4]) & (v <= mode[5])
    else:
        k = (s <= mode[1]) & (v >= mode[2])
    if k.sum() < 50:
        return None
    px, vv = sub[k], v[k]
    lit = px[vv >= np.percentile(vv, 50)]
    prev = a * 0.3
    m = np.zeros(a.shape[:2], bool)
    m[y0:y1:st, x0:x1:st][:k.shape[0], :k.shape[1]] = k
    for _ in range(st):                      # dilate so sparse samples stay visible
        m = m | np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)
    prev[m] = a[m]
    return dict(n=int(k.sum()), median=hexs(np.median(px, 0)), lit=hexs(np.median(lit, 0))), prev


def data_uri(img, w=340):
    im = img if isinstance(img, Image.Image) else Image.fromarray((img * 255).astype("uint8"))
    im = im.convert("RGB")
    im = im.resize((w, int(im.height * w / im.width)))
    b = io.BytesIO(); im.save(b, "JPEG", quality=72)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def swatch(hx, label):
    return (f'<div class="sw"><div style="background:{hx}"></div><small>{label}<br>{hx}</small></div>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=config.DEFAULT_CAR)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--pdf")
    args = ap.parse_args()

    cdir = config.car_dir(args.car)
    man_path = cdir / "calibration.json"
    man = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {"entries": []}
    pdir = cdir / man.get("photos_dir", "sources/photos")
    pdir.mkdir(parents=True, exist_ok=True)
    colors = json.loads((config.car_data(args.car) / "car_colors.json").read_text(encoding="utf-8"))
    meta = config.car_meta(args.car)

    if args.fetch:
        for e in man["entries"]:
            for p in e["photos"]:
                f = pdir / p["file"]
                if not f.exists() and p.get("url"):
                    req = urllib.request.Request(p["url"], headers={"User-Agent": "Mozilla/5.0"})
                    f.write_bytes(urllib.request.urlopen(req, timeout=30).read())
                    print("fetched", f.name)

    results, rows = [], []
    for e in man["entries"]:
        match = [c for c in colors if c["car_code"] == e["car_code"] and e.get("year") in (None, c["year"])]
        if not match:
            print("! no chip", e["car_code"]); continue
        c = match[0]
        card = c.get("measured_hex", c["hex"])
        shots = []
        for p in e["photos"]:
            f = pdir / p["file"]
            if not f.exists():
                print("! missing photo", f.name, "(--fetch downloads it)"); continue
            r = sample(f, p["bbox"], p["mode"])
            if r:
                shots.append((p, r[0], r[1]))
        if not shots:
            continue
        meds = [rgb(s[1]["median"]) for s in shots]
        sug = hexs(np.mean(meds, 0) / 255.0)
        de = delta_e_2000(rgb(card), rgb(sug))
        results.append(dict(car_code=e["car_code"], name=c["name"], card_hex=card, suggested=sug,
                            delta_e=round(de, 1), note=e.get("note", ""),
                            photos=[dict(file=p["file"], url=p.get("url", ""), **r) for p, r, _ in shots]))
        h = (f'<section><h3>{c["name"]} <small>code {e["car_code"]}</small> · ΔE card→suggested '
             f'<b>{de:.0f}</b></h3><p class="n">{e.get("note", "")}</p><div class="row">')
        h += swatch(card, "card chip")
        if c.get("measured_hex"):
            h += swatch(c["hex"], "picked now")
        for i, (p, r, _) in enumerate(shots, 1):
            h += swatch(r["median"], f"photo {i} median") + swatch(r["lit"], f"photo {i} lit half")
        h += swatch(sug, "<b>suggested</b>") + '</div><div class="row imgs">'
        for p, r, prev in shots:
            h += f'<img src="{data_uri(Image.open(pdir / p["file"]))}"><img src="{data_uri(prev)}">'
        h += "</div></section>"
        rows.append(h)

    done = {r["car_code"] for r in results}
    rest = [c for c in colors if c["car_code"] not in done]
    if rest:
        h = '<section><h3>Colours without photo check</h3><p class="n">Card chip, and the colour picked now when it differs.</p><div class="row wrap">'
        seen = set()
        for c in rest:
            if (c["year"], c["car_code"]) in seen: continue
            seen.add((c["year"], c["car_code"]))
            card = c.get("measured_hex", c["hex"])
            h += swatch(card, f'{c["year"]} {c["name"]} · chip')
            if c["hex"] != card:
                h += swatch(c["hex"], "picked now")
        h += "</div></section>"
        rows.append(h)

    css = ("body{font:13px system-ui;margin:24px;color:#222}h1{font-size:22px}h3{margin:0}section{break-inside:avoid;"
           "border:1px solid #ccc;border-radius:6px;padding:10px;margin:12px 0}.n{margin:2px 0 8px;color:#666}"
           ".row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}.row.imgs{margin-top:8px}.row.imgs img{height:130px}"
           ".sw{width:100px;text-align:center}.sw div{height:50px;border:1px solid #888}small{color:#444}")
    html = (f'<!doctype html><meta charset=utf-8><title>{meta.get("display", args.car)} colour calibration</title>'
            f"<style>{css}</style><h1>{meta.get('display', args.car)}: card chips vs real-car photos</h1>"
            "<p class=n>Card chip = measured from the scan. Photo = body pixels of a real car, filtered by hue/brightness "
            "(median and brighter half). Suggested = mean of the photo medians. Estimates: flash and sun clip some colours, "
            "reflections tint others.</p>" + "".join(rows))
    out_html = config.car_data(args.car) / "calibration_report.html"
    out_html.write_text(html, encoding="utf-8")
    config.write_json(config.car_data(args.car) / "calibration.json", results)
    print(f"[{args.car}] {len(results)} colours calibrated → {out_html}")

    if args.apply:
        lp = cdir / "card_layout.json"
        layout = json.loads(lp.read_text(encoding="utf-8"))
        sug = {r["car_code"]: r for r in results}
        n = 0
        for card in layout["cards"]:
            for sw in card["swatches"]:
                r = sug.get(sw.get("car_code"))
                if r:
                    sw["hex"] = r["suggested"]
                    sw["hex_note"] = (f"Photo-calibrated ({len(r['photos'])} real-car photo(s)); card scan measured {r['card_hex']}. "
                                      f"{r['note']}").strip()
                    n += 1
        lp.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"applied {n} swatch overrides → {lp}  (now run measure_car.py)")

    if args.pdf:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={args.pdf}", out_html.resolve().as_uri()], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("pdf →", args.pdf)


if __name__ == "__main__":
    main()
