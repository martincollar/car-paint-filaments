# car-paint-filaments

Match factory car paint colors (scanned Ditzler-style color cards) to 3D-print filaments on sale in Czech e-shops. Outputs a self-contained retro-styled HTML catalog per car.

## Current cars

All pages: **[martincollar.github.io/car-paint-filaments](https://martincollar.github.io/car-paint-filaments/)**

| Car | Years | Colors | Page |
|---|---|---|---|
| Hudson Hornet | 1951-1957 | 65 | [hudson](https://martincollar.github.io/car-paint-filaments/hudson/) |
| Toyota Land Cruiser FJ40 | 1964-1977 | — | in progress |
| Plymouth Barracuda | 1970-1974 | 124 | not published yet |

## Quick start

```bash
# One-off setup
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Rebuild everything for an existing car (measurements → matches → HTML)
scripts/rebuild.sh hudson

# Rebuild only matches + HTML (after a filaments.json tweak or a styling change)
scripts/rebuild_html_only.sh hudson

# Fetch the filament catalog from every shop in shops/*.yaml (sitemap discovery, cached)
scripts/fetch_all_shops.sh            # --shop <key>, --dry-run, --refresh, --force
```

## Folder layout

```
car-paint-filaments/
├── .venv/                    # local Python env (requirements.txt)
├── requirements.txt
├── scripts/                  # thin shell runners
│   ├── rebuild.sh <car>              # full pipeline
│   ├── rebuild_html_only.sh <car>    # matches + HTML only
│   ├── fetch_all_shops.sh            # fetch every shop (src/fetch_all.py)
│   ├── build_site.sh                 # assemble _site/ for GitHub Pages from committed outputs
│   └── publish.sh <car>              # commit output + push → Pages workflow deploys
├── shops/                    # one <shop>.yaml per e-shop + _defaults.yaml (shared rules, banned finishes)
├── tests/                    # unit tests for src/shoplib.py
├── src/                      # all Python code
│   ├── config.py                     # central paths; every script imports this
│   ├── color_tools.py                # _load, median_rgb, filament_rgb, delta_e_2000
│   ├── measure_car.py                # car colors from scanned cards → car_colors.json
│   ├── measure_filaments.py          # one filaments.json from every filaments_raw*.json
│   ├── compute_matches.py            # top-K PLA/PETG per car color → matches_<lib>.json
│   ├── prepare_thumbnails.py         # base64 product photos → thumbnails_<lib>.json
│   ├── build_html.py                 # final HTML page → cars/<car>/output/<car>.html
│   ├── fetch_all.py                  # every shop: sitemap → rules → product pages → raw JSON
│   ├── shoplib.py                    # polite HTTP, robots.txt, cache, sitemap, JSON-LD/microdata, rules
│   ├── adapters/                     # upgates/shoptet/generic (sitemap+HTML), shopify, manual (pins)
│   └── fetch_filamentcolors.py       # intl library (FilamentColors.xyz API)
├── filaments/                # SHARED across all cars
│   ├── sources/              # product photos (png/jpg/webp) downloaded from shop CDNs
│   └── data/
│       ├── filaments.json              # measured filaments (brand, material, color, rgb, hex, shop, url, stock; no prices)
│       ├── filaments_raw_*.json        # per-shop raw fetches
│       ├── catalog.lock.json           # accepted / rejected products per shop (review its git diff)
│       └── fetch_report.json           # last fetch health per shop
└── cars/
    └── <car_name>/           # per car
        ├── car.json                     # display name, year span, tagline, source URL template, "publish" flag
        ├── card_layout.json             # list of cards + per-swatch pixel coords
        ├── sources/                     # scanned color cards (jpg/png)
        ├── data/
        │   ├── car_colors.json          # measured car swatches
        │   ├── matches_{cz,intl}.json   # top-K PLA/PETG per color
        │   └── thumbnails_{cz,intl}.json # inline base64 JPEGs for the HTML
        └── output/
            └── <car_name>.html          # final self-contained HTML page
```

**Design rule:** `filaments/` is shared across cars (one filament catalog serves every car). `cars/<name>/` holds everything specific to one paint source.

Every script takes `--car <name>` and defaults to `hudson` (overridable with `CAR=foo python ...`).

## Publishing

Pages are built locally (the filament photos are gitignored, so CI can't rebuild) and committed in `cars/<car>/output/`. On push to `main`, `.github/workflows/pages.yml` runs `scripts/build_site.sh` and deploys to GitHub Pages:

- `https://martincollar.github.io/car-paint-filaments/<car>/`: `<car>.html` (CZ shops)
- `https://martincollar.github.io/car-paint-filaments/<car>/intl.html`: `<car>-intl.html`
- root: index of all cars with `"publish": true` in `car.json`

```bash
scripts/rebuild_html_only.sh hudson && scripts/publish.sh hudson
```

## Scripts, in order

1. **`measure_car.py --car <name>`** — reads `cars/<name>/card_layout.json` (card images + per-swatch cx/cy coordinates) and writes `cars/<name>/data/car_colors.json`.
2. **`fetch_all.py`** — for each `shops/<shop>.yaml`: discover products from the sitemap (or Shopify JSON / pins), filter them by rules, read each product page, download photos into `filaments/sources/` and write `filaments/data/filaments_raw_<shop>.json`. Transparent, natural and silk filaments are never included.
3. **`measure_filaments.py`** — scans every `filaments_raw*.json`, drops banned finishes, measures each image with `color_tools.filament_rgb()`, deduplicates by (library, URL, slug), writes the single `filaments/data/filaments.json`.
4. **`compute_matches.py --car <name>`** — top-5 PLA + top-5 PETG per car color via ΔE2000.
5. **`prepare_thumbnails.py --car <name>`** — base64 JPEGs for the HTML (product photos resized to 100px, white-composited over transparency).
6. **`build_html.py --car <name>`** — final HTML. Reads `car.json` for title, tagline, subtitle etc., so the same code works for any car.

## Adding a new car

1. Create folders:
   ```bash
   mkdir -p cars/<new_car>/{sources,data,output}
   ```
2. Write `cars/<new_car>/car.json`:
   ```json
   {
     "name": "<new_car>",
     "display": "<Display Name>",
     "script_tagline": "<retro script subtitle>",
     "subtitle_source": "<short source description, used in page copy>",
     "years": [1961, 1962, 1963],
     "card_source_url": "https://example.com/{year}-cards",
     "badge_label": "<DISPLAY>"
   }
   ```
3. Download color cards into `cars/<new_car>/sources/`.
4. Create `cars/<new_car>/card_layout.json` with the pixel coordinates for each swatch:
   ```json
   {
     "box_width": 120, "box_height": 35,
     "source_url_template": "https://example.com/{year}-cards",
     "cards": [
       {
         "card_file": "1961-example-pg01.jpg",
         "box_width": 60, "box_height": 24,
         "swatches": [
           {"cx": 185, "cy":  87, "name": "Sea Mist Green", "year": 1961, "car_code": "G-10", "paint_ref": "12345", "poly": false},
           ...
         ]
       },
       ...
     ]
   }
   ```
   `box_width`/`box_height` on a card are optional and override the file-wide sample box for cards with smaller chips.
5. Run `scripts/rebuild.sh <new_car>` → `cars/<new_car>/output/<new_car>.html`.

The filament catalog is reused as-is; no need to re-fetch unless you want fresh stock status or new products.

## Key implementation notes (bugs found the hard way)

- **PNG transparency**: Many e-shop PNGs use palette mode with a `transparency` entry; `PIL.Image.convert("RGB")` on these returns the first palette color (often green or black), *not* the actually rendered pixel. `color_tools._load()` detects alpha / palette-transparency and composites over white first.
- **Dominant-hue extraction**: For colored filaments, read the median of pixels within ±15° of the saturation²-weighted hue peak, excluding studio-white background, cardboard boxes (hue 15-45° at v < 0.65), yellow watermarks (hue 42-62° at s > 0.4) and gray pixels (s < 0.10, their hue is numerical noise and otherwise dominates).
- **Neutral filaments** (beige, cream, gray, white) use plain median of non-background pixels instead of dominant hue — their saturation is too low for the hue approach.
- **ΔE2000 vs vision**: ΔE weights lightness heavily, so a bright yellow may score closer to a beige than a muted peach. For HTML display, a primary with ΔE ≥ 12 gets a "no close match" banner, and up to 4 alternatives are shown when their ΔE < max(10, primary + 2).
- **Real names**: pages show the real make/model, colour names and codes from the cards, and credit the card source. Third-party affiliate/tracking codes are stripped from shop links (`build_html.clean_url()`).

## Dependencies

Runtime: Python 3.11, pillow, numpy, colour-science, pyyaml. All in `requirements.txt`.

Nothing else outside the virtualenv — HTML is self-contained (no external JS, images embedded as base64) and the only external resources it loads are Google Fonts for the retro type pair.
