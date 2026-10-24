#!/usr/bin/env bash
# Download a car's scanned color cards into cars/<car>/sources/.
# Reads years, pages_per_year and card_image_url_pattern from cars/<car>/car.json.
# Skips files already on disk; a page that 404s upstream is reported and skipped.
# Usage: scripts/fetch_car_cards.sh [car]     (defaults to $CAR, then doppler)
set -euo pipefail
CAR="${1:-${CAR:-doppler}}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
META="$HERE/cars/$CAR/car.json"
OUT="$HERE/cars/$CAR/sources"

[ -f "$META" ] || { echo "no car.json at $META" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }
mkdir -p "$OUT"

PATTERN="$(jq -r '.card_image_url_pattern' "$META")"
n_ok=0; n_skip=0; n_miss=0

for Y in $(jq -r '.years[]' "$META"); do
  PAGES="$(jq -r --arg y "$Y" '.pages_per_year[$y] // empty' "$META")"
  [ -n "$PAGES" ] || { echo "? $Y: no pages_per_year entry, skipping"; continue; }
  for ((i = 1; i <= PAGES; i++)); do
    PAGE="$(printf '%02d' "$i")"
    URL="${PATTERN//\{year\}/$Y}"
    URL="${URL//\{page:02d\}/$PAGE}"
    FILE="$OUT/$(basename "$URL")"
    if [ -s "$FILE" ]; then n_skip=$((n_skip + 1)); continue; fi
    code="$(curl -sSL --retry 2 --retry-delay 2 -o "$FILE.part" -w '%{http_code}' "$URL")" || code=000
    if [ "$code" = "200" ] && [ -s "$FILE.part" ]; then
      mv "$FILE.part" "$FILE"
      echo "✓ $(basename "$FILE")  $(wc -c < "$FILE" | tr -d ' ') bytes"
      n_ok=$((n_ok + 1))
    else
      rm -f "$FILE.part"
      echo "✗ $(basename "$FILE")  HTTP $code"
      n_miss=$((n_miss + 1))
    fi
    sleep 0.4
  done
done

echo "✓ $CAR: $n_ok fetched, $n_skip already present, $n_miss missing — $OUT"
