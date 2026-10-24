"""Unit tests for src/build_html.py and src/compute_matches.py (no catalogue files).

    .venv/bin/python -m unittest discover -s tests
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import build_html, compute_matches
from color_tools import delta_e_2000


class CleanUrl(unittest.TestCase):
    def url(self, u, slug="x-1"):
        return build_html.clean_url({"url": u, "slug": slug})

    def test_tracking_params_dropped(self):
        self.assertEqual(self.url("https://shop.example/p/red?utm_source=fc&variant=7&gclid=1"),
                         "https://shop.example/p/red?variant=7")

    def test_amazon_ref_path(self):
        self.assertEqual(self.url("https://www.amazon.com/dp/B0X/ref=sr_1_1?tag=aff-20"),
                         "https://www.amazon.com/dp/B0X")

    def test_shortener_falls_back_to_swatch(self):
        self.assertEqual(self.url("https://amzn.to/3abc", slug="sunlu-red-12"),
                         "https://filamentcolors.xyz/swatch/sunlu-red-12/")

    def test_non_http_scheme_never_reaches_href(self):
        for bad in ("javascript:alert(1)", "data:text/html,x", ""):
            self.assertTrue(self.url(bad, slug="s").startswith("https://filamentcolors.xyz/"), bad)


class PageBits(unittest.TestCase):
    def test_de_class(self):
        self.assertEqual([build_html.de_class(x) for x in (1.9, 2, 5, 8, 11.99, 12)],
                         ["exc", "vg", "ok", "weak", "weak", "bad"])

    def test_source_host(self):
        self.assertEqual(build_html.source_host("https://www.autocolorlibrary.com/pages/1952-hudson"),
                         "autocolorlibrary.com")
        self.assertEqual(build_html.source_host(""), "")

    def test_banner_only_at_no_match(self):
        def cand(dE): return {"delta_e": dE, "slug": "s", "brand": "B", "material": "PLA",
                              "color_name": "C", "hex": "#000000", "shop": "Smart3D", "url": "https://x.example/"}
        self.assertIn("no-match", build_html.filament_column([cand(12.0)], "PLA", {}))
        self.assertNotIn("no-match", build_html.filament_column([cand(11.9)], "PLA", {}))

    def test_render_is_a_full_document_with_credit(self):
        m = {"name": "Gulf Green", "year": 1952, "car_code": "Q-115", "paint_ref": "41206",
             "hex": "#3A5F4B", "rgb": [58, 95, 75], "source_url": "https://www.autocolorlibrary.com/pages/1952-hudson",
             "pla": [], "petg": []}
        page = build_html.render("hudson", "cz", [m], {}, [],
                                 {"display": "Hudson", "card_source_url": "https://www.autocolorlibrary.com/pages/{year}-hudson"})
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("</head>", page); self.assertIn("<body>", page)
        self.assertIn('href="https://www.autocolorlibrary.com/"', page)
        self.assertIn('href="https://www.autocolorlibrary.com/pages/1952-hudson"', page)


class TopK(unittest.TestCase):
    def test_vectorised_equals_pairwise_sort(self):
        pool = [{"slug": f"f{i}", "rgb": [(i * 37) % 256, (i * 91) % 256, (i * 53) % 256]} for i in range(80)]
        pool.append({"slug": "dup", "rgb": pool[3]["rgb"]})          # a tie: pool order must win
        target = [130, 90, 40]
        old = sorted(((delta_e_2000(target, f["rgb"]), f) for f in pool), key=lambda x: x[0])[:6]
        new = compute_matches.topk(target, pool, k=6)
        self.assertEqual([f["slug"] for _, f in old], [f["slug"] for f in new])
        self.assertEqual([round(d, 2) for d, _ in old], [f["delta_e"] for f in new])

    def test_empty_pool(self):
        self.assertEqual(compute_matches.topk([1, 2, 3], []), [])


if __name__ == "__main__":
    unittest.main()
