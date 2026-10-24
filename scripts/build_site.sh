#!/usr/bin/env bash
# Assemble the GitHub Pages site in _site/ from committed car outputs (no rebuild).
# Every cars/<car>/car.json with "publish": true contributes
#   output/<car>.html       → _site/<car>/index.html
#   _site/<car>/intl.html   redirects to <car>/?region=int (old link of the former separate intl page)
# A car may list old folder names in "redirect_from": each gets _site/<old>/{index,intl}.html that forward to the new URL.
# plus _site/index.html, copied from site/index.html (built by src/build_index.py: one tile per published car).
# Used by .github/workflows/pages.yml and as a local check in scripts/publish.sh.
# Usage: scripts/build_site.sh [out_dir]     (defaults to _site)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$HERE/_site}"
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT"
n=0

for META in "$HERE"/cars/*/car.json; do
  [ "$(jq -r '.publish // false' "$META")" = "true" ] || continue
  CAR="$(basename "$(dirname "$META")")"
  SRC="$(dirname "$META")/output"
  [ -f "$SRC/$CAR.html" ] || { echo "✗ $CAR is published but $SRC/$CAR.html is missing — build it first" >&2; exit 1; }
  mkdir -p "$OUT/$CAR"
  cp "$SRC/$CAR.html" "$OUT/$CAR/index.html"
  cat > "$OUT/$CAR/intl.html" <<REDIR
<!doctype html>
<meta charset="utf-8">
<title>Moved</title>
<meta http-equiv="refresh" content="0; url=./?region=int">
<script>location.replace("./?region=int")</script>
<p>This page moved to <a href="./?region=int">the international shops view</a>.</p>
REDIR
  echo "✓ $CAR → $CAR/"
  for OLD in $(jq -r '.redirect_from[]? // empty' "$META"); do
    mkdir -p "$OUT/$OLD"
    for PAGE in index intl; do
      [ "$PAGE" = "index" ] && TARGET="../$CAR/" || TARGET="../$CAR/?region=int"
      cat > "$OUT/$OLD/$PAGE.html" <<REDIR
<!doctype html>
<meta charset="utf-8">
<title>Moved</title>
<meta http-equiv="refresh" content="0; url=$TARGET">
<link rel="canonical" href="$TARGET">
<script>location.replace("$TARGET" + location.search + location.hash)</script>
<p>This page moved to <a href="$TARGET">$TARGET</a>.</p>
REDIR
    done
    echo "✓ $OLD → $CAR (redirect)"
  done
  n=$((n + 1))
done

[ "$n" -gt 0 ] || { echo "✗ no car has \"publish\": true in car.json" >&2; exit 1; }

# the root page is built locally (src/build_index.py needs the car data) and committed
[ -f "$HERE/site/index.html" ] || { echo "✗ site/index.html is missing — run: .venv/bin/python src/build_index.py" >&2; exit 1; }
cp "$HERE/site/index.html" "$OUT/index.html"
echo "✓ site: $n car(s) → $OUT"
