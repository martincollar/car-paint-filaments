"""Measure the median colour of each Unimog chip scan (solid swatch) and
compare to the RAL-derived placeholder. Run with the project venv.

  python -I measure_chips.py <src_dir> <chips_subdir>
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))  # not used; keep -I clean
SRC = Path(sys.argv[1])                 # project src/ dir
CHIPS = Path(sys.argv[2])               # dir of chip jpgs
sys.path.insert(0, str(SRC))
import numpy as np
from color_tools import _load, rgb_to_hex, hex_to_rgb, rgb_to_lab, delta_e_2000

# chip filename -> (name, code, ral, placeholder_hex)
META = {
    "db1600":  ("Curry yellow",       "DB 1600", "RAL 1027", "#A38C15"),
    "db1624":  ("Amber yellow",       "DB 1624", None,        "#D4A03A"),
    "db2550":  ("Yellow orange",      "DB 2550", "RAL 2000",  "#ED760E"),
    "db2603":  ("Brown orange",       "DB 2603", "RAL 2011",  "#E25303"),
    "db6277":  ("Lorry green",        "DB 6277", None,        "#566B5E"),
    "ral6014": ("NATO green",         "DB 6431", "RAL 6014",  "#47402E"),
    "db6821":  ("Sap green",          "DB 6821", None,        "#5C6B2E"),
    "db7187":  ("Lorry grey",         "DB 7187", None,        "#6F7268"),
    "ral1004": ("Chrome yellow",      "MB 1227", "RAL 1004",  "#E2A900"),
    "db1448":  ("Brown beige",        "DB 1448", "RAL 1011",  "#8A6642"),
    "db1474":  ("Desert sand",        "DB 1474", None,        "#CBB487"),
    "db2553":  ("Red orange",         "DB 2553", "RAL 2001",  "#C93C20"),
    "db3534":  ("Fire red",           "DB 3534", "RAL 3000",  "#AF2B1E"),
    "db5361":  ("Gentian blue",       "DB 5361", "RAL 5010",  "#0E294B"),
    "db6294":  ("Moss green",         "DB 6294", "RAL 6005",  "#2F4538"),
    "db6840":  ("Light yellow green", "DB 6840", None,        "#9DA33C"),
    "db7701":  ("Pebble grey",        "DB 7701", "RAL 7032",  "#B8B799"),
    "db9136":  ("Grey-white",         "DB 9136", "RAL 9002",  "#D7D7D7"),
}

ORDER = ["db1600","db1624","db2550","db2603","db6277","ral6014","db6821","db7187",
         "ral1004","db1448","db1474","db2553","db3534","db5361","db6294","db6840",
         "db7701","db9136"]

def measure(path):
    im = _load(path)
    h, w, _ = im.shape
    # central 60% box, avoids any scan edge/border
    y0, y1 = int(h*0.2), int(h*0.8)
    x0, x1 = int(w*0.2), int(w*0.8)
    patch = im[y0:y1, x0:x1].reshape(-1, 3)
    med = np.median(patch, axis=0)
    return tuple(int(round(c)) for c in med)

rows = []
for key in ORDER:
    name, code, ral, placeholder = META[key]
    p = CHIPS / f"{key}.jpg"
    med = measure(p)
    hexv = rgb_to_hex(med)
    lab_m = rgb_to_lab(med)
    lab_p = rgb_to_lab(np.array(hex_to_rgb(placeholder), dtype=float))
    de = delta_e_2000(lab_m, lab_p)
    rows.append({"key":key,"name":name,"code":code,"ral":ral,
                 "measured":hexv,"placeholder":placeholder,"deltaE":round(float(de),1)})
    print(f"{name:20s} {code:8s} {ral or '-':9s} measured {hexv}  placeholder {placeholder}  dE {de:4.1f}")

Path(sys.argv[3]).write_text(json.dumps(rows, indent=2) + "\n")
print("\nwrote", sys.argv[3])
