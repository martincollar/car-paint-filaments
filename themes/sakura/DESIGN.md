# Sakura design language

Source of truth: `tokens.css` (`--dl-*`, scoped `.theme-sakura, .tile--sakura`). Visual reference: `styleguide.html` (`python src/build_styleguide.py --theme sakura`).

- **Mood:** rising sun on washi paper. Quiet, soft, Japanese-print: pale rays from a small red sun in the corner, indigo ink type. Red is a spark (sun, short title bar, hover), never the main colour.
- **Palette:** page `#f6f1ea`, card `#fffdf9`, primary indigo `#2b3a67` (deep `#1a2342`), accent sun red `#c8102e` (deep `#8d0a20`), trim gold `#e0b25a`, ray/petal pink `#f2b8c0` (weak `#f8dde1`), ink `#1f2433`, rule `#dcd6cc`, muted `#6c6f78`.
- **Fonts:** title Reggae One, tagline and UI Barlow Condensed (uppercase, wide tracking), body Barlow.
- **Shapes:** radius 18 px, 1 px rules, soft shadow (no hard offset shadows: that is Torq). Buttons are indigo pills, hover turns red.
- **Tile:** `tile.html` = `.t-clip` (clips rays + sun to the card) with `.t-rays` (`repeating-conic-gradient` from the top-right corner, masked to fade) and `.t-sun` (red disc, cream ring). `--sun` sets the disc size. The car overflows the frame.
- **Header card (detail page):** `tile--sakura head-card`, same builder as Doppler/Torq, bigger sun, filters inside under a hairline.
- **Table:** on the paper, soft: hairline rows, round swatches, small indigo year badge with a red bar.

## Adopting this in a new car
Copy `tokens.css`, `tile.css`, `tile.html`, `headcard.css`, `tile-fonts.txt`, rewrite values, set `"theme"` in `car.json`.
