# Default design language

Source of truth: `tokens.css` (`--dl-*`, scoped `.theme-default, .tile--default`). This is the look of every car whose `car.json` has no `"theme"`; Doppler, Torq and Sakura pick their own.

- **Mood:** plain and quiet. Cool grey, a white table, hairline rules, no decoration, so the paint colours are the only colour on the page.
- **Palette:** page `#e2e5e8`, tile and header card `#eceef0`, table `#ffffff`, ink `#1b2127`, muted `#5d6671`, rule `#cdd2d8`, accent graphite `#3a4550` (deep `#232b33`). Green, amber and red appear only on the ΔE figures.
- **Fonts:** IBM Plex Sans for everything (title 600 with -0.025em tracking), IBM Plex Mono for codes, hex values, refs and shop tags. Sentence case, no all-caps labels.
- **Shapes:** radius 14 px card with a 1 px grey border and a soft shadow; buttons are outlined graphite pills that fill on hover; swatches are rounded squares with a 1 px border.
- **Tile (homepage):** `tile.css` on the shared neutral tile; no `tile.html`, so no decoration. The car sits on the grey and recolours on hover like every other tile.
- **Header card (detail page):** `tile--default head-card`, same builder as Doppler and Torq; title, tagline and meta, then the region switch and year jump under a hairline.
- **Table:** white, flat, hairline rows; the year heading is a large semibold number with a quiet "Model year" next to it.

## Adopting this in a new car
Do nothing: a car without `"theme"` gets this look. To make a car look different, copy `tokens.css`, `tile.css`, `headcard.css`, `theme.css`, `fonts.txt` into `themes/<name>/`, rewrite the values, set `"theme": "<name>"` in `car.json`.
