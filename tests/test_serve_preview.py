import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import serve_preview


class Selectors(unittest.TestCase):
    def test_tile_and_header_card_selectors(self):
        m = serve_preview.SELECTOR.match(".tile--doppler.head-card .tile-name")
        self.assertEqual((m.group(1), bool(m.group(2))), ("doppler", True))
        m = serve_preview.SELECTOR.match(".tile--doppler .tile-name")
        self.assertEqual((m.group(1), bool(m.group(2))), ("doppler", False))
        self.assertIsNone(serve_preview.SELECTOR.match(".tile--doppler.head-card .a .b"))


if __name__ == "__main__":
    unittest.main()
