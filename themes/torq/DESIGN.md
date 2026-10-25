# Torq design language

Source of truth: `tokens.css` (`--dl-*`, scoped `.theme-torq, .tile--torq`). Visual reference: `styleguide.html` (`python src/build_styleguide.py --theme torq`).

- **Mood:** 1970s muscle car. Hard edges, ink outlines, hard offset shadows, red/white stripes, the stars-and-stripes shield.
- **Palette:** bg `#dedede`, primary red `#d9432b` (deep `#a82c17`), accent blue `#27407a` (deep `#172a58`), trim gold `#f0b429`, ink and outline `#111`, paper `#fff`.
- **Fonts:** title Russo One (white fill, 2-3 px ink stroke, `paint-order: stroke fill`, hard shadow), tagline and UI Barlow Condensed, body Barlow.
- **Shapes:** radius 0; card 4 px ink border with `8px 8px 0` shadow and a 22 px red/white stripe on top; buttons are red rectangles with 3 px ink border and `3px 3px 0` shadow, hover turns blue; tagline is a black parallelogram (`clip-path`).
- **Header card (detail page):** `tile--torq head-card`, same builder as Doppler, shield top right, filters inside. It sits on the page background, above the paper.
- **Table:** on the striped paper, flat: hairline rows, square ink-bordered swatches, plain coloured ΔE text.

## Adopting this in a new car
Copy `tokens.css`, `tile.css`, `tile.html`, `headcard.css`, rewrite values, set `"theme"` in `car.json`.
