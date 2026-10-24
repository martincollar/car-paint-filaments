"""Unit tests for src/build_html.py and src/compute_matches.py (no catalogue files).

    .venv/bin/python -m unittest discover -s tests
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import build_html, compute_matches, prepare_hero
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

    def test_shortener_has_no_link(self):
        self.assertEqual(self.url("https://amzn.to/3abc"), "#")

    def test_non_http_scheme_never_reaches_href(self):
        for bad in ("javascript:alert(1)", "data:text/html,x", ""):
            self.assertEqual(self.url(bad), "#", bad)


class PageBits(unittest.TestCase):
    def test_de_class(self):
        self.assertEqual([build_html.de_class(x) for x in (1.9, 2, 5, 8, 11.99, 12)],
                         ["exc", "vg", "ok", "weak", "weak", "bad"])

    def test_banner_only_at_no_match(self):
        def cand(dE): return {"delta_e": dE, "slug": "s", "brand": "B", "material": "PLA",
                              "color_name": "C", "hex": "#000000", "shop": "Smart3D", "url": "https://x.example/"}
        self.assertIn("no-match", build_html.filament_column([cand(12.0)], "PLA", {}))
        self.assertNotIn("no-match", build_html.filament_column([cand(11.9)], "PLA", {}))

    def test_render_is_a_full_document_without_card_source(self):
        m = {"name": "Gulf Green", "year": 1952, "car_code": "Q-115", "paint_ref": "41206",
             "hex": "#3A5F4B", "rgb": [58, 95, 75], "source_url": "https://www.autocolorlibrary.com/pages/1952-hudson",
             "pla": [], "petg": []}
        page = build_html.render("hudson", {"eu": [m], "int": [m]}, {}, [],
                                 {"display": "Hudson", "card_source_url": "https://www.autocolorlibrary.com/pages/{year}-hudson"})
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn("</head>", page); self.assertIn("data-region=\"eu\"", page)
        self.assertNotIn("autocolorlibrary", page)


class RegionPage(unittest.TestCase):
    def fil(self, slug, regions):
        return {"slug": slug, "brand": "B", "material": "PLA", "color_name": slug, "shop": "S", "url": "https://s.example/" + slug,
                "hex": "#336699", "rgb": [51, 102, 153], "regions": regions}

    def test_candidates_are_in_their_region_only_and_switch_is_present(self):
        eu, bambu = self.fil("eu-only", ["eu"]), self.fil("int-only", ["int"])
        m = {"name": "Blue", "year": 1952, "car_code": "B", "paint_ref": "1", "hex": "#336699", "rgb": [51, 102, 153],
             "source_url": "https://x.example", "petg": []}
        page = build_html.render("c", {"eu": [{**m, "pla": [{"delta_e": 0.5, **eu}]}],
                                       "int": [{**m, "pla": [{"delta_e": 0.5, **bambu}]}]},
                                 {}, [eu, bambu], {"display": "C"})
        self.assertRegex(page, r'(?s)<div class="rcols" data-r="eu">(?:(?!</article>).)*eu-only')
        self.assertRegex(page, r'(?s)<div class="rcols" data-r="int">(?:(?!</article>).)*int-only')
        self.assertIn('data-region-btn="int"', page)

    def test_compute_matches_in_region(self):
        fs = [self.fil("a", ["eu"]), self.fil("b", ["int"]), self.fil("c", ["eu", "int"])]
        self.assertEqual([f["slug"] for f in compute_matches.in_region(fs, "eu")], ["a", "c"])
        self.assertEqual([f["slug"] for f in compute_matches.in_region(fs, "int")], ["b", "c"])


class HeroPreview(unittest.TestCase):
    HERO = {"photo": "data:image/jpeg;base64,AA==", "mask": "data:image/png;base64,AA==",
            "roof": "#ffffff", "credit": "Maker <b>", "credit_url": "https://maker.example/p"}

    def test_no_hero_adds_nothing(self):
        self.assertEqual(build_html.hero_parts(None), ("", "", ""))

    def test_hero_page_has_canvas_and_escaped_credit(self):
        css, html, js = build_html.hero_parts(self.HERO)
        self.assertIn('id="hero-canvas"', html)
        self.assertIn("Maker &lt;b&gt;", html)
        self.assertIn('href="https://maker.example/p"', html)
        self.assertNotIn("__HERO__", js)

    def test_unsafe_credit_url_is_neutralised(self):
        _, html, _ = build_html.hero_parts(dict(self.HERO, credit_url="javascript:alert(1)"))
        self.assertNotIn("javascript:", html)

    def test_script_cannot_be_closed_by_data(self):
        _, _, js = build_html.hero_parts(dict(self.HERO, photo="</script><script>x"))
        self.assertNotIn("</script><script>x", js)

    def test_filament_swatches_are_pickable(self):
        c = {"delta_e": 1.0, "slug": "s", "brand": "B", "material": "PLA", "color_name": "C",
             "hex": "#112233", "shop": "Smart3D", "url": "https://x.example/"}
        row = build_html.filament_column([c], "PLA", {})
        self.assertIn('data-hex="#112233"', row)
        self.assertIn('<a class="pick" href="https://x.example/"', row)   # a real link: focusable, keyboard-pickable


class HeroPrepare(unittest.TestCase):
    def test_resize_keeps_aspect(self):
        from PIL import Image
        out = prepare_hero._resize(Image.new("RGB", (1900, 1217)), 1000)
        self.assertEqual(out.size, (1000, 641))

    def test_uris_are_data_uris(self):
        from PIL import Image
        im = Image.new("RGB", (4, 4), "#336699")
        self.assertTrue(prepare_hero.photo_uri(im).startswith("data:image/jpeg;base64,"))
        self.assertTrue(prepare_hero.mask_uri(im).startswith("data:image/png;base64,"))


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
