"""Preview server for the root page (and any static folder): never lets the browser cache (plain `http.server` sends
Last-Modified, so Chrome keeps showing an old page after a rebuild), and serves the layout editor.

`<page>?edit` loads scripts/layout_editor.js: drag, resize and recolour the tile's elements, press "Uložit" and the
changes are written to `themes/<theme>/tile-offsets.css` (all widths) or `tile-offsets-mobile.css` (window <= 520 px)
for position and size, and `tile-colors.css` for colours; then `src/build_index.py` is run. Saving is accepted from
localhost only.

Usage: .venv/bin/python scripts/serve_preview.py <directory> [port]      (default port 8765)
"""
import functools, http.server, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELECTOR = re.compile(r"^\.tile--([a-z0-9_-]+) \.[a-z0-9_-]+$")
PX = r"-?\d+(?:\.\d+)?px"
TRANSLATE = re.compile(rf"^{PX} {PX}$")
ORIGIN = {"center", "left center"}
OFFSET_LINE = re.compile(rf"^(.+?) \{{ translate: ({PX} {PX});(?: scale: ([\d.]+);)?(?: rotate: (-?[\d.]+)deg;)?(?: transform-origin: ([a-z ]+);)? \}}$")
COLOR_LINE = re.compile(r"^(.+?) \{ (background|color): (#[0-9a-fA-F]{6}); \}$")


def theme_dir(theme):
    folder = ROOT / "themes" / theme
    if not re.fullmatch(r"[a-z0-9_-]+", theme) or not folder.is_dir():
        raise ValueError(f"unknown theme {theme!r}")
    return folder


def write_rules(path, lines):
    if lines:
        path.write_text("".join(f"{line}\n" for line in sorted(lines)), encoding="utf-8")
    elif path.exists():
        path.unlink()


def save_offsets(data):
    mobile = data.get("scope") == "mobile"
    for theme, rules in data.get("themes", {}).items():
        path = theme_dir(theme) / ("tile-offsets-mobile.css" if mobile else "tile-offsets.css")
        current = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                m = OFFSET_LINE.match(line)
                if m:
                    current[m.group(1)] = line
        for selector, r in rules.items():
            m = SELECTOR.match(selector)
            scale, rotate = float(r.get("scale", 1)), float(r.get("rotate", 0))
            if (not m or m.group(1) != theme or not TRANSLATE.match(r["translate"]) or not 0.2 <= scale <= 4
                    or not -360 <= rotate <= 360 or r.get("origin") not in ORIGIN):
                raise ValueError(f"bad rule {selector!r}: {r!r}")
            body = f"translate: {r['translate']};"
            if abs(scale - 1) > 0.004:
                body += f" scale: {round(scale, 2)};"
            if abs(rotate) > 0.04:
                body += f" rotate: {round(rotate, 1)}deg;"
            if len(body) > len(f"translate: {r['translate']};"):
                body += f" transform-origin: {r['origin']};"
            if body == "translate: 0px 0px;":
                current.pop(selector, None)
            else:
                current[selector] = f"{selector} {{ {body} }}"
        write_rules(path, list(current.values()))
    by_theme = {}
    for c in data.get("colors", []):
        m = SELECTOR.match(c["selector"])
        if not m or c["prop"] not in ("background", "color") or not re.fullmatch(r"#[0-9a-fA-F]{6}", c["value"]):
            raise ValueError(f"bad colour {c!r}")
        by_theme.setdefault(m.group(1), []).append(c)
    for theme, items in by_theme.items():
        path = theme_dir(theme) / "tile-colors.css"
        current = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                m = COLOR_LINE.match(line)
                if m:
                    current[(m.group(1), m.group(2))] = line
        for c in items:
            current[(c["selector"], c["prop"])] = f"{c['selector']} {{ {c['prop']}: {c['value'].lower()}; }}"
        write_rules(path, list(current.values()))
    done = subprocess.run([sys.executable, str(ROOT / "src" / "build_index.py")], cwd=ROOT, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(done.stderr.strip()[-400:])


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?")[0] == "/__editor.js":
            body = (ROOT / "scripts" / "layout_editor.js").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path != "/__save_offsets" or self.client_address[0] not in ("127.0.0.1", "::1"):
            self.send_error(403)
            return
        try:
            save_offsets(json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)))))
            out = {"ok": True}
        except Exception as e:                       # report to the editor panel instead of a bare 500
            out = {"ok": False, "error": str(e)}
        body = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else "."
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
    http.server.ThreadingHTTPServer(("", port), functools.partial(Handler, directory=directory)).serve_forever()
