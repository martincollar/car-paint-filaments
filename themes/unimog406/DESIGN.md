# Mogster design language

Source of truth: `tokens.css` (`--dl-*`, scoped `.theme-unimog406, .tile--unimog406`).

- **Mood:** rugged off-road utility truck, not a show car. Concrete/sand ground, a spec-sheet feel,
  stencil-style titles, one hard safety-orange accent instead of chrome or gloss.
- **Palette:** bg `#ddd7c8` / page `#e8e3d6` (concrete/sand, echoes the product photo's neutral studio
  floor), paper `#fbfaf5`, ink `#211e1a`. Primary safety-orange `#c0421f` (deep `#8f2f15`) is lifted
  straight from the Mogster's own red-orange wheels, the one fixed colour on every variant regardless
  of body paint. Accent olive-steel `#525b48` (deep `#363d30`) nods to the chassis/running-gear colour;
  accent2 warm grey `#8f8a76` is quiet trim.
- **Fonts:** title Bebas Neue (tall, condensed, stencil-like — reads like equipment markings), tag/UI
  Oswald (condensed, utilitarian), body IBM Plex Sans (clean technical sans, keeps long ΔE tables
  legible), mono IBM Plex Mono for codes/hex values.
- **Shapes:** radius 6px (machined, not round, not sharp), 2px ink border, a small hard offset shadow
  (`3px 3px 0` buttons, `6px 6px 0` cards) — a plate bolted down, not a floating card.
- **Structure:** `theme.css` and `headcard.css` are copied unchanged from the default theme (layout,
  year-nav, region switch, table rules, hero-preview chrome) — every visual difference comes from
  `tokens.css` alone. Only the `.theme-default` selectors in headcard.css were renamed to
  `.theme-unimog406`.
- **Not yet done:** `tile.css` / `tile.html` for the root-page tile (the car is unpublished, so this
  isn't needed yet); `styleguide.html` (`python src/build_styleguide.py --theme unimog406`).

## Adopting this in a new car
Copy `tokens.css`, `theme.css`, `headcard.css`, `fonts.txt`, rewrite `tokens.css`'s values (and rename
the `.theme-default` selectors in headcard.css to the new theme name), set `"theme"` in `car.json`.
