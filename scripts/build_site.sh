#!/usr/bin/env bash
# Assemble the GitHub Pages site in _site/ from committed car outputs (no rebuild).
# Every cars/<car>/car.json with "publish": true contributes
#   output/<car>.html       → _site/<car>/index.html
#   output/<car>-intl.html  → _site/<car>/intl.html   (if built)
# plus _site/index.html linking to each car by its `display` name.
# Used by .github/workflows/pages.yml and as a local check in scripts/publish.sh.
# Usage: scripts/build_site.sh [out_dir]     (defaults to _site)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$HERE/_site}"
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT"
links=""
n=0

for META in "$HERE"/cars/*/car.json; do
  [ "$(jq -r '.publish // false' "$META")" = "true" ] || continue
  CAR="$(basename "$(dirname "$META")")"
  SRC="$(dirname "$META")/output"
  [ -f "$SRC/$CAR.html" ] || { echo "✗ $CAR is published but $SRC/$CAR.html is missing — build it first" >&2; exit 1; }
  mkdir -p "$OUT/$CAR"
  cp "$SRC/$CAR.html" "$OUT/$CAR/index.html"
  intl=""
  if [ -f "$SRC/$CAR-intl.html" ]; then
    cp "$SRC/$CAR-intl.html" "$OUT/$CAR/intl.html"
    intl=" <a class=\"intl\" href=\"$CAR/intl.html\">international shops</a>"
  fi
  DISPLAY="$(jq -r '.display // .name' "$META")"
  TAGLINE="$(jq -r '.script_tagline // ""' "$META")"
  links+="<li><a href=\"$CAR/\">$DISPLAY</a> <span>$TAGLINE</span>$intl</li>"$'\n'
  echo "✓ $CAR → $CAR/"
  n=$((n + 1))
done

[ "$n" -gt 0 ] || { echo "✗ no car has \"publish\": true in car.json" >&2; exit 1; }

cat > "$OUT/index.html" <<HTML
<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Car paint filaments</title>
<style>
  body { font: 18px/1.5 Georgia, serif; max-width: 36rem; margin: 3rem auto; padding: 0 16px; background: #f6efe2; color: #2b2118; }
  a { color: #8a2c1c; } span { color: #7a6a58; font-style: italic; margin-left: .4em; }
  .intl { font-size: .8em; margin-left: .6em; } li { margin: .5em 0; }
</style>
<h1>Car paint filaments</h1>
<p>Vintage paint colours matched to PLA / PETG filaments you can buy today.</p>
<ul>
$links</ul>
HTML
echo "✓ site: $n car(s) → $OUT"
