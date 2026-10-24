"""Unit tests for the palette choice in src/build_index.py (no catalogue files).

    .venv/bin/python -m unittest discover -s tests
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import build_index
from color_tools import delta_e_2000, hex_to_rgb


def cand(hx, de, name="x"):
    return {"hex": hx, "delta_e": de, "brand": "B", "color_name": name}


MATCHES = {
    "eu": [{"pla": [cand("#FF0000", 1.0, "red"), cand("#FE0101", 1.5, "red2"), cand("#0000FF", 2.0, "blue")],
            "petg": [cand("#00FF00", 3.0, "green")]}],
    "int": [{"pla": [cand("#FF0000", 0.5, "red"), cand("#EEEE00", 20.0, "far")], "petg": []}],
}


class Palette(unittest.TestCase):
    def test_hex_not_repeated_and_no_near_duplicates(self):
        pal = build_index.pick_palette(MATCHES)
        hexes = [p["hex"] for p in pal]
        self.assertEqual(len(hexes), len(set(hexes)))
        for i, a in enumerate(hexes):
            for b in hexes[i + 1:]:
                self.assertGreaterEqual(delta_e_2000(hex_to_rgb(a), hex_to_rgb(b)), build_index.MIN_SPACING)

    def test_best_first_and_poor_matches_left_out(self):
        pal = build_index.pick_palette(MATCHES)
        self.assertEqual(pal[0]["hex"], "#FF0000")
        self.assertNotIn("#EEEE00", [p["hex"] for p in pal])      # ΔE 20 > MAX_MATCH_DE
        self.assertNotIn("#FE0101", [p["hex"] for p in pal])      # indistinguishable from #FF0000

    def test_primary_first_even_when_not_a_candidate(self):
        pal = build_index.pick_palette(MATCHES, primary="#123456")
        self.assertEqual(pal[0], {"hex": "#123456", "label": ""})
        self.assertIn("#FF0000", [p["hex"] for p in pal])

    def test_primary_label_from_candidate(self):
        pal = build_index.pick_palette(MATCHES, primary="#0000ff")
        self.assertEqual(pal[0], {"hex": "#0000FF", "label": "B blue"})

    def test_size_cap(self):
        self.assertEqual(len(build_index.pick_palette(MATCHES, size=2)), 2)

    def test_named_palette_order_and_best_year(self):
        matches = {"eu": [
            {"name": "Lemon Twist", "year": 1970, "pla": [cand("#F6CE00", 1.7, "a")]},
            {"name": "Lemon Twist", "year": 1973, "pla": [cand("#F5DA3D", 1.8, "b")]},
            {"name": "Royal Red", "year": 1954, "pla": [cand("#531C21", 2.4, "c")]}]}
        pal = build_index.named_palette(matches, ["Royal Red", "lemon twist"])
        self.assertEqual([p["hex"] for p in pal], ["#531C21", "#F6CE00"])      # given order, closest year wins
        pal = build_index.named_palette(matches, ["Lemon Twist 1973"])
        self.assertEqual(pal[0]["hex"], "#F5DA3D")                              # explicit year
        with self.assertRaises(ValueError):
            build_index.named_palette(matches, ["Nope"])

    def test_neon_filament_loses_to_a_normal_one(self):
        colour = {"name": "Dull Green", "year": 1970, "rgb": [90, 110, 80],
                  "pla": [dict(cand("#00FF00", 1.0, "neon"), neon=True), cand("#5A6E50", 3.0, "plain")]}
        pal = build_index.named_palette({"eu": [colour]}, ["Dull Green"])
        self.assertEqual(pal[0]["hex"], "#5A6E50")                              # penalised although its ΔE is lower
        colour["rgb"] = [0, 255, 0]                                              # a neon paint: no penalty
        self.assertEqual(build_index.named_palette({"eu": [colour]}, ["Dull Green"])[0]["hex"], "#00FF00")

    def test_year_span(self):
        self.assertEqual(build_index.year_span([1974, 1970]), "1970–74")
        self.assertEqual(build_index.year_span([1999, 2001]), "1999–2001")
        self.assertEqual(build_index.year_span([1960]), "1960")


if __name__ == "__main__":
    unittest.main()
