#!/usr/bin/env bash
# Commit a car's built HTML and push; .github/workflows/pages.yml deploys it.
# The car must have "publish": true in cars/<car>/car.json to appear on the site.
# Usage: scripts/publish.sh [car_name]       (defaults to doppler)
set -euo pipefail

CAR="${1:-doppler}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
src="$HERE/cars/$CAR/output/$CAR.html"

[ -f "$src" ] || { echo "no $src — build it first (scripts/rebuild_html_only.sh $CAR)" >&2; exit 1; }
[ "$(jq -r '.publish // false' "$HERE/cars/$CAR/car.json")" = "true" ] \
  || echo "! $CAR has no \"publish\": true in car.json — committed, but it won't appear on the site" >&2

"$HERE/scripts/build_site.sh" >/dev/null   # same assembly CI runs; fails early if anything is missing

cd "$HERE"
git add "cars/$CAR/output" "cars/$CAR/car.json"
if git diff --cached --quiet; then
  echo "no changes to publish"
  exit 0
fi
git commit -m "publish $CAR $(date +%F)"
git push
echo "published → https://martincollar.github.io/car-paint-filaments/$CAR/ in ~1 min (Actions → pages)"
