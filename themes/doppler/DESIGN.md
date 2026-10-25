# Doppler design language

Source of truth: `tokens.css` (`--dl-*`, scoped `.theme-doppler, .tile--doppler`). Visual reference: `styleguide.html` (`python src/build_styleguide.py --theme doppler`).

- **Mood:** 1950s dealer banner. Warm cream card, teal bubble title, red arrow ribbon, sparkle star, pill buttons with a hard foot.
- **Palette:** bg `#f5e8bd`, primary teal `#2f8f8a` (deep `#0a6361`), accent red `#d2452f` (deep `#8e2a1a`), trim mustard `#e9a73a`, ink `#1d4a52`, paper `#fffdf4`, outline `#111`.
- **Fonts:** title Lobster Two italic 700, tagline Barlow Condensed italic 800, UI Oswald, body Fraunces.
- **Shapes:** radius 22 px card with a double inner ring (3 px teal border, mustard inset line); buttons are pills with `0 3px 0` deep-teal foot, hover turns red.
- **Header card (detail page):** `tile--doppler head-card`, built by `tile_parts.head_card_html`, styled by `tile.css` + `headcard.css`. Title bubble, ribbon, meta line, then region switch and year jump inside the card. It sits on the page background, above the paper.
- **Table:** lives on the punched-hole paper, flat: hairline rows, square swatches, plain coloured ΔE text, no card per filament.

## Recipes (don't redo)
- Bubble = SVG data-URI background stretched with `preserveAspectRatio="none"`, `vector-effect: non-scaling-stroke` (the hexes inside the data URI cannot use variables; keep them equal to `--dl-primary` / `--dl-paper`).
- White outline plus hard black shadow = `filter: drop-shadow(...)` on a pseudo-element, never on the heading.
- Ribbon = two pseudo-elements with `clip-path` (white one larger, red one) and the shadow on the unclipped parent.
- Title letters are `span.ch` with `--i`/`--n`, bent with `calc()`.

## Adopting this in a new car
Copy `tokens.css`, `tile.css`, `tile.html`, `headcard.css`, `tile-fonts.txt`, rewrite the values and shapes, set `"theme"` in `car.json`.
