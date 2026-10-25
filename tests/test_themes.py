import re, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

REQUIRED = ["bg", "card", "ink", "primary", "primary-deep", "accent", "accent-deep", "paper", "shadow", "radius",
            "border", "font-title", "font-tag", "font-ui", "font-body"]
CARS = ["doppler", "torq"]


class Tokens(unittest.TestCase):
    def test_tokens_complete(self):
        for car in CARS:
            css = (ROOT / "themes" / car / "tokens.css").read_text()
            for name in REQUIRED:
                self.assertRegex(css, rf"--dl-{name}:", f"{car} lacks --dl-{name}")


class Styleguide(unittest.TestCase):
    def test_lists_every_token_and_section(self):
        import build_styleguide
        for car in CARS:
            page = build_styleguide.build(car)
            for name in build_styleguide.tokens_of(car):
                self.assertIn(name, page)
            for word in ("Buttons", "Header card", "Table row"):
                self.assertIn(word, page)


if __name__ == "__main__":
    unittest.main()
