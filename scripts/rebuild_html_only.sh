#!/usr/bin/env bash
# Only recompute matches + rebuild HTML (skip remeasure), for both libraries.
set -euo pipefail
CAR="${1:-hudson}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$HERE/.venv/bin/python}"
[ -x "$PY" ] || { echo "no $PY — run: python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2; exit 1; }
"$PY" "$HERE/src/prepare_hero.py"       --car "$CAR"
for LIB in cz intl; do
  "$PY" "$HERE/src/compute_matches.py"    --car "$CAR" --library "$LIB"
  "$PY" "$HERE/src/prepare_thumbnails.py" --car "$CAR" --library "$LIB"
  "$PY" "$HERE/src/build_html.py"         --car "$CAR" --library "$LIB"
done
echo "✓ cars/$CAR/output/{$CAR.html,$CAR-intl.html}"
