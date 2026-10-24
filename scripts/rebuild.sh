#!/usr/bin/env bash
# Rebuild everything for one car (full pipeline; one page with a region switch).
set -euo pipefail
CAR="${1:-doppler}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$HERE/.venv/bin/python}"
[ -x "$PY" ] || { echo "no $PY — run: python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2; exit 1; }

echo "→ measuring car swatches ($CAR)"
"$PY" "$HERE/src/measure_car.py"        --car "$CAR"
echo "→ measuring all filaments"
"$PY" "$HERE/src/measure_filaments.py"
echo "→ preparing hero preview ($CAR)"
"$PY" "$HERE/src/prepare_hero.py"       --car "$CAR"
echo "→ computing matches (per region)"
"$PY" "$HERE/src/compute_matches.py"    --car "$CAR"
echo "→ preparing thumbnails"
"$PY" "$HERE/src/prepare_thumbnails.py" --car "$CAR"
echo "→ building HTML"
"$PY" "$HERE/src/build_html.py"         --car "$CAR"
echo "✓ done — cars/$CAR/output/$CAR.html"
