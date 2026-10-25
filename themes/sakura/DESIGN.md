# Sakura design language

Source of truth: `tokens.css` (`--dl-*`, scoped `.theme-sakura, .tile--sakura`). Visual reference: `styleguide.html` (`python src/build_styleguide.py --theme sakura`).

- **Mood:** "Sakura Run" Japanese street-culture screen print. Cream paper with print specks, black ink type, blossom pink, a cherry branch, falling petals, a black kana sign. Decorative Japanese lettering only (not meant as copy).
- **Palette:** page `#fbf6ea`, card/paper `#f4ecda` / `#fffdf6`, ink `#17130f` (also primary), sun red-pink `#e8506a` (deep `#b92e48`), blossom pink `#f4a3b1` (weak `#fadde1`), rule `#d9cdb4`, muted `#6b6154`.
- **Fonts:** title Dela Gothic One (ink, hard pink shadow), brush kana Yuji Boku, tagline and UI Barlow Condensed (tagline italic 800 on a skewed pink slab), body Barlow.
- **Shapes:** radius 6 px, 3 px ink borders, hard pink offset shadow (`7px 7px 0`, buttons `3px 3px 0`); buttons are ink rectangles, hover turns sun red.
- **Tile:** `tile.html` = `.t-clip` (clips the SVG `.t-art`: striped sun, ink branch, three blossom colours, buds, loose petals; `--art` sets its size), `.t-sign` (black vertical kana box), `.t-vert` (tiny vertical caption on the left edge, hidden in the header card). Paper specks = an SVG `feTurbulence` data-URI on `.tile-frame`; the threshold is the last two numbers of its `feColorMatrix` (lower = fewer specks).
- **Header card (detail page):** `tile--sakura head-card`, bigger art, filters under a 3 px ink rule.
- **Table:** on the paper (3 px ink border), flat: hairline rows, rounded-square swatches, plain coloured ΔE text, year number in the title font with a pink shadow.

## Adopting this in a new car
Copy `tokens.css`, `tile.css`, `tile.html`, `headcard.css`, `tile-fonts.txt`, rewrite values, set `"theme"` in `car.json`.
