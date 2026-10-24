"""Central path configuration for the project.

Folder layout:
    car-paint-filaments/
      src/                 — shared Python code
      scripts/             — thin runner scripts
      filaments/           — SHARED filament catalog (all cars share one)
        sources/           — product photos (png/jpg/webp)
        data/              — filaments.json, filaments_raw_*.json
      cars/<car_name>/     — one folder per car / color card source
        car.json           — car metadata (name, year range, source URLs)
        sources/           — scanned color cards (jpg/png)
        data/              — car_colors.json, matches.json, thumbnails.json
        output/            — <car_name>.html

Add a new car:
    mkdir cars/<name>/{sources,data,output}
    echo '{"name":"<Display>","display":"<Display>","years":[...]}' > cars/<name>/car.json
    # then run per-car scripts with --car <name>
"""
from __future__ import annotations
import os, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FILAMENTS_SOURCES = ROOT / "filaments" / "sources"
FILAMENTS_DATA    = ROOT / "filaments" / "data"
FILAMENTS_JSON    = FILAMENTS_DATA / "filaments.json"
FILAMENT_COLOR_OVERRIDES = ROOT / "filaments" / "color_overrides.json"
FILAMENTS_CACHE   = ROOT / "filaments" / ".cache"          # HTTP cache, not versioned
CATALOG_LOCK      = FILAMENTS_DATA / "catalog.lock.json"   # discovered product URLs per shop
FETCH_REPORT      = FILAMENTS_DATA / "fetch_report.json"   # last fetch health per shop

SHOPS_DIR         = ROOT / "shops"                          # one <shop>.yaml per e-shop
SHOP_DEFAULTS     = SHOPS_DIR / "_defaults.yaml"            # rules shared by every shop

CARS_DIR = ROOT / "cars"

def car_dir(car: str) -> Path:    return CARS_DIR / car
def car_sources(car: str) -> Path: return car_dir(car) / "sources"
def car_data(car: str) -> Path:    return car_dir(car) / "data"
def car_output(car: str) -> Path:  return car_dir(car) / "output"
def car_meta(car: str) -> dict:
    p = car_dir(car) / "car.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def list_cars():
    return sorted(d.name for d in CARS_DIR.iterdir() if d.is_dir() and (d / "car.json").exists())

# Convenience: default car (for scripts that only serve one at a time)
DEFAULT_CAR = os.environ.get("CAR", "hudson")

if __name__ == "__main__":
    print(f"ROOT:              {ROOT}")
    print(f"FILAMENTS_SOURCES: {FILAMENTS_SOURCES}")
    print(f"FILAMENTS_DATA:    {FILAMENTS_DATA}")
    print(f"Cars:              {list_cars()}")
    print(f"Default CAR env:   {DEFAULT_CAR}")
