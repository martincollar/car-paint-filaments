#!/usr/bin/env bash
# Fetch the filament catalog from every shop in shops/*.yaml (polite: robots.txt,
# Crawl-delay, HTTP cache — known pages are re-read only after `refresh_days`).
# Extra args go to src/fetch_all.py, e.g. --shop hubacek3d, --dry-run, --refresh.
# Exits non-zero when a shop failed or tripped the shrink guard (see filaments/data/fetch_report.json).
# After this, review `git diff filaments/data/catalog.lock.json` and run `scripts/rebuild.sh <car>`.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$HERE/.venv/bin/python}"
[ -x "$PY" ] || { echo "no $PY — run: python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2; exit 1; }

"$PY" "$HERE/src/fetch_all.py" "$@"
echo "✓ all shops done — review: git diff filaments/data/catalog.lock.json — then run scripts/rebuild.sh <car>"
