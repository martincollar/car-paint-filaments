# Unimog 406/416 (1963–1970) — colour sources (reconnaissance)

Not yet a built car: this is the raw colour material pulled in so we can measure
real hexes. No `car.json` / `card_layout.json` yet.

## Chip scans — `sources/chips/*.jpg`  (tracked)
Scanned original Unimog colour chips from rockymountainmoggers.com (`/pix/<code>.jpg`),
credited there to Ron DePugh. The page warns they are a close approximation only
(monitor/scan drift). 18 colours: the 6-colour standard range of the era plus the
extra-cost / special colours. Filenames are the DB code (`db6277.jpg`), except NATO
green and chrome yellow which the page files under their RAL number (`ral6014`, `ral1004`).

## Per-colour reference images — `sources/refcars/404<code>.gif`  (tracked)
One image per factory colour from the same page: a 404-series body recoloured in that
colour. Useful as a colour-on-vehicle reference, not real 406/416 photos.

## Real 406/416 photos — `sources/photos/*.jpg`  (gitignored, third-party)
Wikimedia Commons (see each file's Commons page for licence/author). The `photos/`
dir is gitignored by project convention (third-party, re-downloadable); URLs recorded
here so they can be re-fetched:
- `1976_unimog_406.jpg`        — commons File:1976 Unimog 406 (7316378108).jpg  (blue, gentian-blue family)
- `unimog_museum_gaggenau.jpg` — commons File:Gaggenau 2016 -Unimog-Museum- by-RaBoe 052.jpg
- `unimog_muenster.jpg`        — commons File:Unimog at Münster Nienberge.jpg

## Measured hexes — `data/chip_measurements.json`  (tracked)
Median of the central 60% of each chip scan (project `color_tools`). ΔE2000 vs the
earlier RAL/placeholder guess is recorded per colour.

### Caveats worth a second look before trusting the chip value
Scan drift shows up on a few. Flag for re-check (measure from a better chip, or
override from the RAL standard / a real photo):
- Sap green DB 6821 — chip reads teal `#39A17E`; saftgrün is normally a yellow-olive green (ΔE 10 off the guess).
- Desert sand DB 1474 — chip reads dark olive `#857856`, darker than a sand colour should be.
- Red orange DB 2553 — chip reads very red `#CE3436`, closer to red than orange.
- NATO green / gentian blue — chip reads lighter than the RAL standard.

Colours that match the RAL standard closely (ΔE < 2): lorry green, moss green,
lorry grey, grey-white — trust the chip.

## Factory range of the era (for card_layout later)
Standard six (Wikipedia, 1970s range): lorry green, sap green, lorry grey,
brown orange, amber yellow, curry yellow. Plus the extra-cost specials above.
Wheels: Kaminrot RAL 3002 / Beerenrot DB 3605 (→ black with disc brakes ~1973).
Chassis: Tiefschwarz RAL 9005.
