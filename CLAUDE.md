# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Always use the in-project venv (`./.venv/bin/python`), never the system Python or `~/.venvs/hudson/` from the project's earlier life.

```bash
# One-off setup after a fresh clone
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Full rebuild for one car (measures swatches, measures all filaments, matches, thumbnails, HTML)
scripts/rebuild.sh <car_name>              # defaults to doppler

# HTML-only rebuild (after a filaments.json tweak, build_html.py styling, or car.json edit)
scripts/rebuild_html_only.sh <car_name>

# Publish: commit cars/<car>/output and push; .github/workflows/pages.yml deploys (asks first: it pushes)
scripts/publish.sh <car_name>

# Fetch the filament catalog from every shop in shops/*.yaml (polite + cached; first run is slow)
scripts/fetch_all_shops.sh                 # extra args: --shop <key>, --dry-run, --refresh, --force

# Unit tests (shoplib: rules, finish ban, sitemap, extraction — no network)
.venv/bin/python -m unittest discover -s tests

# Run one stage manually
.venv/bin/python src/<stage>.py --car <car_name>
```

Only `src/shoplib.py` has unit tests. Everything else is verified manually: open `cars/<name>/output/<name>.html` in a browser (or republish the Claude artifact) and check that the primary filament picks look right against the car swatches.

## Architecture

**Two data worlds, one pipeline.** The project matches a car's paint catalog against a filament catalog. The filament catalog is global (one shared pool serves every car); the paint catalog is per-car. The folder layout mirrors that split exactly:

- `filaments/{sources,data}/` — shared product photos and the single `filaments.json`.
- `cars/<name>/{sources,data,output}/` + `car.json` + `card_layout.json` — everything specific to one paint source.

Every script that needs paths imports `src/config.py`, which exposes `FILAMENTS_SOURCES`, `FILAMENTS_JSON`, and `car_sources(name) / car_data(name) / car_output(name) / car_meta(name)`. Nothing else should hard-code paths. `DEFAULT_CAR` reads the `CAR` env var and falls back to `doppler`.

**Pipeline stages, in order:**

1. `fetch_all.py` (one `shops/<shop>.yaml` per shop) → `filaments/data/filaments_raw_<shop>.json` + photos in `filaments/sources/`, plus `catalog.lock.json` and `fetch_report.json`. `fetch_filamentcolors.py` stays separate (intl library, same `shoplib.http_get` + shrink guard, keeps the old file when a page fails).
2. `measure_filaments.py` globs **every** `filaments_raw*.json`, drops banned finishes, measures each image, dedupes by (library, URL, slug) → `filaments/data/filaments.json`
3. `measure_car.py --car <name>` reads `cars/<name>/card_layout.json` (per-swatch cx/cy coordinates), crops each sample from its card scan, writes `cars/<name>/data/car_colors.json`
4. `compute_matches.py --car <name>` → top-K PLA + top-K PETG per color via ΔE2000
5. `prepare_thumbnails.py --car <name>` → inline base64 JPEGs of the filament photos (self-contained HTML)
6. `prepare_hero.py --car <name>` → `cars/<name>/data/hero.json` (optional, only when `car.json` has `hero`; see below)
7. `build_html.py --car <name>` → `cars/<name>/output/<name>.html`

**Adding a new car** must not require editing any code in `src/`. The whole per-car customization is: `cars/<new_name>/car.json` (display name, tagline, years, source URL template, badge label), `cars/<new_name>/card_layout.json` (card images + swatch coordinates), and the card scans in `cars/<new_name>/sources/`. Then `scripts/rebuild.sh <new_name>`. Keep this contract — if a new car requires a code change, that's a bug in the generic pipeline, not a reason to special-case the car.

**Adding a new shop** must not require code either, if its platform is known: write `shops/<key>.yaml` (`name`, `platform`, `base`, `sitemap`, `include` regex for product URLs), run `src/fetch_all.py --shop <key> --dry-run` to check the candidate list, then a real run. Add a `.shop-tag.shop-<slugified name>` CSS block in `build_html.py`. Platforms (`src/adapters/`): `upgates` / `shoptet` / `generic` = sitemap + one product page each (JSON-LD → microdata → `<h1>`/og); `shopify` = `/products.json`; `manual` = only `pins:`. A shop on a new platform that has a sitemap and schema.org markup works as `generic`. Record shape downstream: `{slug, brand, material, color_name, shop, url, image_url, local_image, availability, stock, title, last_ok, stale?}` (no `price`, see below).

Current shops (`shops/*.yaml`): Smart3D, Aurapol, Hubacek3D (upgates); 3DFox (shoptet, **3dfoxshop.cz**, not 3dfox.cz); Fillamentum (shopify); FilamentPM, 3DJake (generic, 3DJake limited to Fiberlogy because of its 10 s Crawl-delay); Prusa3D, Na3D (manual — Prusa's sitemap only has parent pages, the colour is a variant).

**No prices, anywhere.** The pipeline deliberately does not scrape, store, hard-code, or display filament prices. That covers no `extract_price()` in fetchers, no `price` key in any record or JSON, no price columns in fetcher logs, and no prices or currency in the HTML. Prices change constantly, discounts make them wrong within days, and the old hard-coded "749 Kč" for Prusament was already stale. The shop link on each candidate is the source of truth. Don't add prices back when writing a new fetcher or touching `build_html.py`.

**Two libraries, side by side.** Every filament record carries a `library` field — `"cz"` for the Czech shop pool (`shops/*.yaml`), `"intl"` for FilamentColors.xyz. `compute_matches.py`, `prepare_thumbnails.py` and `build_html.py` all take `--library cz|intl` and write side-by-side artifacts: `cars/<car>/data/matches_<lib>.json`, `thumbnails_<lib>.json`, and `output/<car>.html` (cz, kept legacy name) vs `output/<car>-intl.html`. `scripts/rebuild.sh` runs both. The intl library (`fetch_filamentcolors.py`) is special — it hits a REST API (`/api/swatch/`) and keeps the hex that the API already carries, skipping `filament_rgb()` measurement entirely. `measure_filaments.py` recognises records that already have `rgb+hex` and leaves them untouched. The two libraries never mix in a single HTML; the eventual plan is one JS-driven page with a filter, which is why they share the same `filaments.json` but stay partitioned downstream.

## Recolor preview (optional per car)

A car with a `hero` block in `car.json` (`photo`, `mask`, optional `roof` hex, `credit`, `credit_url`) gets a floating car preview: greyed out with a "?" until the user clicks a filament swatch, then recoloured live in the browser (canvas, CIELAB: the photo's lightness variation around the body mean is kept, a/b come from the filament hex). `mask` is an RGB PNG the same size as the photo: R = body paint, G = roof paint (soft edges); everything else (chrome, tyres, glass) is never touched. One photo + one mask per car; no `src/` change to add one. `roof` fixes the roof colour (two-tone cars); without it the roof follows the body. `prepare_hero.py` embeds both at 1000 px. The Doppler (Hudson) hero is a 3D Sets photo (`cars/doppler/sources/hero.jpg`, gitignored via `cars/*/sources/hero.*`): the built HTML and `hero.json` embed it, so **don't publish them without permission from 3D Sets**.

## Non-obvious details

**Publishing: build locally, CI only deploys.** This repo is the single source and the GitHub Pages site (`https://martincollar.github.io/car-paint-filaments/<car>/`, public repo). `filaments/sources/` is gitignored, so CI cannot rebuild: HTML is built locally and committed in `cars/<car>/output/`. On push, `.github/workflows/pages.yml` runs `scripts/build_site.sh`, which copies each car with `"publish": true` in `car.json` to `_site/<car>/index.html` (+ `intl.html`) and writes a root index from `display`/`script_tagline`.

**`color_tools._load()` must composite transparent PNGs over white before converting to RGB.** PIL's `.convert("RGB")` on a palette PNG with a `transparency` entry returns the first palette color (often green or black), not the actually rendered pixel. Several e-shops ship photos in this format. Any new image-reading code must go through `_load()`, not call `Image.open(...).convert("RGB")` directly.

**`filament_rgb()` branches on average saturation after filtering.** Colored filaments use the saturation²-weighted dominant hue of pixels within ±15° of the peak, excluding studio-white background, dark brown cardboard (hue 15-45° at v < 0.65), yellow Smart3D watermarks (hue 42-62° at s > 0.4, but only when that yellow is < 4 % of the foreground — otherwise it *is* the filament; before this rule every yellow filament measured near-black) and gray pixels (s < 0.10, whose "hue" is numerical noise). The colour path needs colourful pixels to be > 2 % of the measured ones (not just > 200), or anti-aliased edges of a removed spool flip a pale winding to "coloured". Neutral filaments fall back to the median of the remaining pixels, minus light kraft (boxes, spool cores) when ≥ 60 % remains and minus dark achromatic spool flanges when ≥ 30 % remains. Changing any threshold shifts many colours at once: **before every measurement change, re-measure the whole cz catalogue against the current `filaments.json` and look at a photo/old/new sheet of everything that moved ΔE ≥ 3** — several plausible-looking fixes this session broke dark browns, blues or tan filaments elsewhere.

**Name hints (`filament_rgb(name=...)`).** `measure_filaments.py` passes the colour name. `neutral_class()` maps it to black / dark (antracit, graphite, tmavě šedá) / white / grey (incl. silver, hliníková) and then measures only dark / v < 0.5 / lit-half light / mid-grey low-saturation pixels with kraft excluded (grey also drops white spool labels). `kraft_like_name()` (beige, brown, tan, gold, pink, peach … families) gates the **kraft second pass**: when > 12 % of the photo is light cardboard and the result is cardboard-coloured but the name is not a cardboard-like colour, the whole brown hue band is dropped and the photo re-measured — accepted only if ≥ 5 % of the foreground remains and the result isn't the black spool (protects tan filaments with unknown names, e.g. Fillamentum "Mukha"). The saturation filter that keeps only strongly saturated pixels in the hue window (orange next to a kraft box) runs only when p90 saturation ≥ 0.75 *and* the photo has kraft; elsewhere it darkened blues by dropping highlights.

**Per-brand hints: `measure_hints` in `shops/_defaults.yaml`** (brand regex → `filament_rgb()` kwargs). Use them when one brand's photos share a prop that defeats the generic rules: `aurapol: {min_chroma: 0.06}` (slightly bluish black spool outvotes pastels; not global because dark bronze/olive have the same tiny chroma), `sunlu: {drop_hue_band: [205, 240, 0.05, 1.0]}` (blue-grey spool with a navy hub). Prefer a hint over a code special case, and an override over a hint for single items.

**`src/review_sheet.py` is the visual check** (`filaments/.cache/review_sheet.html`, opens in the browser): photo next to measured colour, a "Changed by the last measurement" section (`previous_hex`, set by `measure_filaments.py` when a colour moves ΔE ≥ 3), and flags `box` (kraft photo whose result looks like cardboard and name isn't beige/brown) and `cluster` (3+ names of one brand measuring the same). Run it after every measurement or catalogue change; the user reviews colours there.

**`filament_rgb()` cannot always measure white or black filaments, and darkens shaded renders.** Without a name hint a white winding is indistinguishable from the studio background (V > 0.93, S < 0.08) and a black one falls under the shadow cut (V < 0.15), so the median lands on the spool, stand, label or cardboard. Edge-connected background removal doesn't fix this: a white winding sits next to white or grey stands, and a black one next to black flanges. The hue-window median includes the filament's own shadows, so heavily shaded renders come out darker than the lit surface (Prusament Electric Green: #83C59D measured vs #BFEDCC lit). A global "brighter half" measurement was tested and rejected: it changed the primary pick for 44 of 65 Hudson paints and worsened best ΔE for 42 (the lit half is used only for white-named filaments and for hand-made overrides).

**Manual colors go in `filaments/color_overrides.json`** (`{slug: {hex, note}}`, path in `config.FILAMENT_COLOR_OVERRIDES`). `measure_filaments.py` applies them after measuring, sets `confidence: "manual_override"`, keeps the measured value as `measured_hex`, and warns about override slugs that no longer exist. After dedup it also prints `! suspicious measurement` for any measured record whose name says white/black but whose lightness contradicts it (L < 75 / L > 30). Treat each warning as a to-do: crop the winding in the photo, take the median, add an override with a `note` saying where the hex came from. Transparent filaments (e.g. Fillamentum PETG Natural) can't be measured from a photo at all; leave them alone rather than guessing.

**ΔE2000 weights lightness over hue.** A bright yellow may score numerically closer to a beige than a muted peach does. In the HTML, the primary candidate is always shown; up to 4 alternatives follow when their ΔE < max(10, primary + 2), and a red "no close match" banner sits above a primary with ΔE ≥ 12 (`NO_MATCH_DE`). Don't change either threshold without visually inspecting the resulting pairs.

**Shops are discovered from sitemaps, filtered by rules, and reviewed through a lockfile.** `fetch_all.py` reads each shop's sitemap, keeps URLs matching `include` and none of `exclude` (`_defaults.yaml` + shop) whose path names PLA/PETG, then reads each product page. Rules, not code, keep out the noise: samples, bundles, 2.85 mm, 3+ kg, CF/wood/glow, multicolour/thermo, non-PLA/PETG. `pins:` are hand-written products. On `manual` shops (Prusa3D, Na3D) they are the whole catalogue; on the others they are the old per-script slug lists, migrated, and discovery finds them anyway — the pin only keeps brand/material/color_name/local_image (and so the measured colour) stable. Pins skip include/exclude and the title check (not the finish ban), so never pin something the rules would reject (2.85 mm, 0.5 kg, ASA, HT-PLA as its own material); `overrides:` (by slug) fix a discovered item or `skip` it. Each run rewrites `filaments/data/catalog.lock.json` (accepted products + rejected slugs with reason); **review its git diff before rebuilding**, that's where new and vanished filaments show up.

**Banned finishes: transparent, natural, silk.** The user never prints with them. `exclude_finishes` in `shops/_defaults.yaml` (diacritics-folded regexes, so "průhledná", "čirá", "přírodní", "hedvábná" match) is applied to slug, URL, title and colour name of every record — pins included — in `fetch_all.py`, and again in `measure_filaments.py`, which also covers the intl library. Don't pin or override one back in.

**Fetching is polite and loss-free.** `shoplib.http_get()` obeys robots.txt `Disallow` and `Crawl-delay` (min 0.5 s, cap 20 s per host), retries 429/5xx with backoff, and caches bodies in `filaments/.cache/` (gitignored) with ETag/Last-Modified. Known pages are re-read only after `refresh_days` (7) unless the sitemap `lastmod` is newer; never-seen pages are capped by `max_new_per_run` (300), so the first crawl of a big shop spreads over runs (`--max-new N` overrides). A page that errors keeps its previous record with `stale: true`; a 404, or a redirect to a non-product page (3DJake sends dead slugs to search, whose og:image is the shop logo), drops it. A shop whose record count would fall below `min_keep_ratio` (80 %) is not written (`--force` to accept). Availability comes from schema.org markup, not from grepping "Skladem" (which appears in every page's menu). Product names come from JSON-LD/`<h1>` before og:title, and `clean_title()` strips promo prices ("jen za 298 Kč") and emoji.

**Single-theme light-only page.** The HTML commits to one paper-cream look, no dark mode. All colors live in `:root` only — do not add `@media (prefers-color-scheme: dark)` or `[data-theme="dark"]` blocks (they were removed on purpose). Years are listed newest-first in the main loop and in year navigation; keep that order.

**Public naming.** Pages use `display` from `car.json` (Hudson's is "3D Sets Doppler", matching its preview photo), the real colour names and codes from the cards, and do **not** name or link the card library (`autocolorlibrary.com`): that host stays in code and data (`card_source_url`, `source_url`, fetch/measure scripts) only, never in generated HTML. Don't invent fictional car names or brands. What must stay out of published pages are third-party affiliate/tracking codes on shop links: `build_html.clean_url()` strips them.

**Thumbnails cost context in the HTML.** The page is self-contained with ~500-750 KB of base64 image data (filament photos only); keep thumbnail max_dim at 100-200 px and quality 70-78, and never embed raw card scans. If size balloons unexpectedly, check for transparent PNGs being compressed poorly after the white composite.

## Other agent configs on this machine

The user has Codex and Gemini CLI user-level configs at `~/.codex/config.toml` and `~/.gemini/settings.json`. If you want to import their MCP servers / slash commands / instructions into Claude Code, reply `/import` to see what's importable, then `/import --yes=<digest>`. Don't read those files or write Claude config by hand.
