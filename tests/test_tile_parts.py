import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import tile_parts


class SplitName(unittest.TestCase):
    def test_one_span_per_letter(self):
        out, n = tile_parts.split_name("Torq")
        self.assertEqual(n, 4)
        self.assertEqual(out.count('class="ch"'), 4)
        for i in range(4):
            self.assertIn(f"--i:{i}", out)

    def test_words_kept_together_and_space_counted(self):
        out, n = tile_parts.split_name("3D Sets")
        self.assertEqual(n, 7)
        self.assertEqual(out.count('class="w"'), 2)
        self.assertIn("--i:3", out)


class HeadCard(unittest.TestCase):
    def test_structure(self):
        out = tile_parts.head_card_html("torq", "Torq", "Tag", "<b>m</b>", "<svg/>", "<nav/>")
        for needle in ('class="page-head tile tile--torq head-card"', "tile-frame", "tile-deco", '<h1 class="tile-name"',
                       "tile-tag", "tile-meta", "head-filters", "<svg/>", "<nav/>", "<b>m</b>"):
            self.assertIn(needle, out)

    def test_no_filters_row_when_empty(self):
        out = tile_parts.head_card_html("torq", "Torq", "Tag", "m", "", "")
        self.assertNotIn("head-filters", out)


if __name__ == "__main__":
    unittest.main()
