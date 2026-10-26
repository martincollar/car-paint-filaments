"""Unit tests for src/color_tools.py on synthetic photos (no real catalogue needed).

    .venv/bin/python -m unittest discover -s tests
"""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import numpy as np
from PIL import Image
import color_tools as ct


def photo(tmp, name, size=(200, 200), bg=(255, 255, 255), patches=(), mode="RGB"):
    """Save a synthetic product photo: `bg` plus `patches` [(x0, y0, x1, y1, rgb), …]."""
    a = np.empty((size[1], size[0], 3), dtype=np.uint8); a[:] = bg
    for x0, y0, x1, y1, rgb in patches:
        a[y0:y1, x0:x1] = rgb
    p = Path(tmp) / name
    Image.fromarray(a).convert(mode).save(p)
    return p


class Load(unittest.TestCase):
    def test_palette_png_with_transparency_is_composited_over_white(self):
        with tempfile.TemporaryDirectory() as tmp:
            im = Image.new("P", (10, 10), 0)
            im.putpalette([0, 200, 0] + [255, 0, 0] * 255)   # index 0 green = transparent
            im.paste(1, (0, 0, 5, 10))                         # left half: opaque red
            im.info["transparency"] = 0
            p = Path(tmp) / "pal.png"; im.save(p, transparency=0)
            a = ct._load(p)
            self.assertEqual(tuple(a[5, 2]), (255, 0, 0))
            self.assertEqual(tuple(a[5, 8]), (255, 255, 255))   # not the green palette entry


class FilamentRgb(unittest.TestCase):
    def test_coloured_winding_on_white(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = photo(tmp, "red.png", patches=[(50, 50, 150, 150, (200, 30, 40))])
            rgb, n = ct.filament_rgb(p)
            self.assertLess(ct.delta_e_2000(rgb, (200, 30, 40)), 1.0)
            self.assertEqual(n, 100 * 100)

    def test_orange_next_to_kraft_box(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = photo(tmp, "orange.png", patches=[(10, 20, 90, 180, (190, 150, 105)),     # kraft box
                                                  (110, 20, 190, 180, (240, 110, 10))])  # orange
            rgb, _ = ct.filament_rgb(p, name="Orange")
            self.assertLess(ct.delta_e_2000(rgb, (240, 110, 10)), 3.0)

    def test_white_winding_with_name_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = photo(tmp, "white.png", bg=(255, 255, 255),
                      # a shaded white winding (V 0.88, below the studio-white cut) + a dark stand
                      patches=[(40, 40, 160, 160, (225, 223, 218)), (0, 0, 200, 20, (60, 60, 60))])
            rgb, _ = ct.filament_rgb(p, name="Bílá")
            self.assertGreater(ct.rgb_to_lab(rgb)[0], 85)

    def test_nothing_measurable_is_none_not_black(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = photo(tmp, "blank.png")
            self.assertEqual(ct.filament_rgb(p), (None, 0))


class Names(unittest.TestCase):
    def test_neutral_class(self):
        for name, cls in [("Černá", "black"), ("Jet Black", "black"), ("Antracit", "dark"),
                          ("Bílá", "white"), ("Stříbrná", "grey"), ("Cloud Nine", None)]:
            self.assertEqual(ct.neutral_class(name), cls, name)

    def test_kraft_like_name(self):
        self.assertTrue(ct.kraft_like_name("Béžová"))
        self.assertTrue(ct.kraft_like_name("Coffee Brown"))
        self.assertFalse(ct.kraft_like_name("Signal White"))


class Conversions(unittest.TestCase):
    def test_hex_round_trip(self):
        self.assertEqual(ct.hex_to_rgb("#AABBCC"), [170, 187, 204])
        self.assertEqual(ct.hex_to_rgb("aabbcc"), [170, 187, 204])
        self.assertEqual(ct.rgb_to_hex([170, 187, 204]), "#AABBCC")
        for bad in ("#ABC", "", None, "zzzzzz"):
            self.assertIsNone(ct.hex_to_rgb(bad), bad)

    def test_delta_e_many_matches_pairwise(self):
        rng = np.random.default_rng(0)
        pool = rng.integers(0, 256, size=(50, 3))
        target = [120, 60, 30]
        many = ct.delta_e_2000_many(ct.rgb_to_lab(target), ct.rgb_to_lab(pool))
        one = [ct.delta_e_2000(target, p) for p in pool]
        np.testing.assert_allclose(many, one, rtol=0, atol=1e-9)


if __name__ == "__main__":
    unittest.main()


class LiftWhite(unittest.TestCase):
    RULES = [
        {"match": "ivory|bone", "pull": 0},
        {"match": "traffic|signal", "L": 100, "chroma": 0},
        {"match": "cold", "L": 98, "pull": 0.5},
        {"match": ".", "L": 98, "chroma": 0.15},
    ]

    def lift(self, rgb, name):
        return ct.lift_white(rgb, name, self.RULES)

    def test_plain_white_gets_much_lighter_and_neutral(self):
        out = self.lift([227, 226, 218], "Bílá")
        self.assertGreaterEqual(ct.rgb_to_lab(out)[0], 96)
        self.assertLess(max(out) - min(out), 6)

    def test_traffic_white_is_pure_white(self):
        self.assertEqual(self.lift([210, 208, 203], "Traffic White"), [255, 255, 255])

    def test_cold_white_keeps_its_blue_cast(self):
        out = self.lift([218, 220, 229], "Cold White")
        self.assertLess(ct.rgb_to_lab(out)[2], -1)
        self.assertGreater(ct.rgb_to_lab(out)[0], ct.rgb_to_lab([218, 220, 229])[0])

    def test_offwhite_names_and_non_whites_are_untouched(self):
        self.assertEqual(self.lift([228, 205, 163], "Ivory White"), [228, 205, 163])
        self.assertEqual(self.lift([200, 200, 200], "Light Grey"), [200, 200, 200])

    def test_idempotent_and_never_darkens(self):
        once = self.lift([227, 226, 218], "White")
        self.assertEqual(self.lift(once, "White"), once)
        self.assertEqual(self.lift([255, 255, 255], "White"), [255, 255, 255])
