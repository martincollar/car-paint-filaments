"""Unit tests for src/shoplib.py pure helpers (no network).

    .venv/bin/python -m unittest discover -s tests
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import shoplib


class NeonDetection(unittest.TestCase):
    def test_neon(self):
        for name in ["Žlutá FLUO", "Neon Yellow", "Neonově Žlutá", "Super Žlutá", "Žlutá (Super Yellow)",
                     "Zelená Fluorescenční", "Neon Green UV", "Highlight Yellow", "Magic Neon Mojito"]:
            self.assertTrue(shoplib.is_neon(name), name)
        self.assertTrue(shoplib.is_neon("Žlutá", "devil-design-pla-zluta-super-yellow-1kg"))

    def test_not_neon(self):
        for name in ["Signal Blue", "Lime Green", "Electric Indigo", "Pick Your Poison", "Lemon Yellow",
                     "Červená (Super Red)", "Modrá (Super Blue)", "Žlutá", "Neutral Grey"]:
            self.assertFalse(shoplib.is_neon(name), name)


class FinishFilter(unittest.TestCase):
    def test_banned(self):
        for text, finish in [
            ("Red Wine Transparent", "transparent"),
            ("aurapol-pla-3d-filament-honey-partially-transparent-1-kg", "transparent"),
            ("filament-aurapol-pla-mint-breeze-castecne-transparentni-1-75-mm-1-kg", "transparent"),
            ("PETG průhledná oranžová", "transparent"),
            ("PLA čirá", "transparent"),
            ("Translucent Light Blue", "transparent"),
            ("pla-extrafill-natural-1kg", "natural"),
            ("Woodjet Natur", "natural"),
            ("PLA přírodní", "natural"),
            ("Almond Silk", "silk"),
            ("refill-azurefilm-pla-silk-olivove-zelena", "silk"),
            ("PLA hedvábná zlatá", "silk"),
        ]:
            self.assertEqual(shoplib.excluded_finish(text), finish, text)

    def test_allowed(self):
        for text in ["Cloud Nine", "Signature Blue", "Circle Green", "Sky Blue", "Frosted Mint",
                     "Pistachio Green", "Light Ivory", "pla-extrafill-traffic-white-1kg"]:
            self.assertIsNone(shoplib.excluded_finish(text), text)


class Rules(unittest.TestCase):
    def setUp(self):
        self.r = shoplib.ShopRules("t", {"name": "T", "platform": "upgates", "regions": ["eu"],
                                         "include": ["^/p/"], "exclude": ["^/p/akce-"]},
                                   shoplib.load_defaults())

    def test_accepts(self):
        self.assertTrue(self.r.accepts("https://x.cz/p/filament-aurapol-pla-cloud-nine-1-75-mm-1-kg"))
        self.assertFalse(self.r.accepts("https://x.cz/sk/p/filament-aurapol-pla-cloud-nine"))
        self.assertFalse(self.r.accepts("https://x.cz/p/akce-filament-pla-red"))
        self.assertFalse(self.r.accepts("https://x.cz/p/filament-pla-red-3kg"))
        self.assertFalse(self.r.accepts("https://x.cz/p/filament-pla-red-2-85-mm-1-kg"))
        self.assertFalse(self.r.accepts("https://x.cz/p/aurapol-pla-vzorek-red"))
        self.assertFalse(self.r.accepts("https://x.cz/p/9-1-box-aurapol-pet-g-filament-white"))
        self.assertFalse(self.r.accepts("https://x.cz/p/filament-pla-cf-black-1kg"))
        self.assertTrue(self.r.accepts("https://x.cz/p/filament-aurapol-asa-cervena-tool-1-75-mm-850g"))
        self.assertFalse(self.r.accepts("https://x.cz/products/asa_cf10-extrafill-black"))
        self.assertFalse(self.r.accepts("https://x.cz/p/aurapol-asa-3d-filament-slate-grey-2000g-1-75-mm"))
        self.assertFalse(self.r.accepts("https://x.cz/p/filament-spectrum-asa-275-kevlar-black"))

    def test_material(self):
        self.assertEqual(self.r.material("/p/aurapol-pet-g-filament-white"), "PETG")
        self.assertEqual(self.r.material("/p/filament-lume-petg-tyrkysova"), "PETG")
        self.assertEqual(self.r.material("Filament LUME PLA+ Tyrkysová"), "PLA+")
        self.assertEqual(self.r.material("/p/filament-aurapol-pla-cloud-nine"), "PLA")
        self.assertEqual(self.r.material("/p/filament-rosa3d-asa-tyrkysova"), "ASA")
        self.assertIsNone(self.r.material("/p/plastova-civka"))

    def test_slug(self):
        self.assertEqual(self.r.slug("https://x.cz/p/abc-def"), "abc-def")
        self.assertEqual(self.r.slug("https://x.cz/abc-def/"), "abc-def")
        r = shoplib.ShopRules("t", {"name": "T", "platform": "generic", "regions": ["eu"],
                                       "slug_regex": r"/([^/]+/p\d+)$"}, {"regions": {"eu": "EU"}})
        self.assertEqual(r.slug("https://www.filament-pm.cz/pla-bila-1-75-mm-1-kg/p61"), "pla-bila-1-75-mm-1-kg/p61")


class Regions(unittest.TestCase):
    D = {"regions": {"eu": "EU / CZ", "int": "INT"}}

    def test_valid_regions_kept_in_order(self):
        self.assertEqual(shoplib.validate_regions(["int", "eu"], self.D, "t"), ["int", "eu"])

    def test_missing_empty_or_unknown_region_is_an_error(self):
        for bad in (None, [], "eu", ["us"], ["eu", "us"]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                shoplib.validate_regions(bad, self.D, "t")

    def test_every_shop_declares_known_regions(self):
        regs = shoplib.shop_regions()
        self.assertTrue(regs)
        self.assertEqual(regs["Prusa3D"], ["eu", "int"])
        self.assertEqual(regs["Smart3D"], ["eu"])


class Sitemap(unittest.TestCase):
    def test_urlset(self):
        xml = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://a.cz/p/x?a=1&amp;b=2</loc><lastmod>2026-10-01</lastmod></url>
          <url><loc><![CDATA[https://a.cz/p/y]]></loc></url></urlset>"""
        kind, entries = shoplib.parse_sitemap(xml)
        self.assertEqual(kind, "urlset")
        self.assertEqual(entries, [("https://a.cz/p/x?a=1&b=2", "2026-10-01"), ("https://a.cz/p/y", None)])

    def test_index(self):
        xml = """<sitemapindex><sitemap><loc>https://a.cz/sitemap-products.xml.gz</loc>
                 <lastmod>2026-10-24</lastmod></sitemap></sitemapindex>"""
        self.assertEqual(shoplib.parse_sitemap(xml),
                         ("index", [("https://a.cz/sitemap-products.xml.gz", "2026-10-24")]))


class Extract(unittest.TestCase):
    def test_jsonld(self):
        html = """<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
          {"@type":"Product","name":"Filament X PLA Red","brand":{"@type":"Brand","name":"X"},
           "image":["/img/red.jpg"],"sku":"R1","offers":{"@type":"Offer","availability":"https://schema.org/OutOfStock"}}]}
        </script>"""
        p = shoplib.extract_product(html, "https://shop.cz/p/red")
        self.assertEqual((p["name"], p["brand"], p["image"], p["availability"], p["sku"]),
                         ("Filament X PLA Red", "X", "https://shop.cz/img/red.jpg", "OutOfStock", "R1"))

    def test_microdata_and_og(self):
        html = """<meta property="og:image" content="https://cdn/x.jpg"><meta property="og:title" content="PLA Mint">
                  <link itemprop="availability" href="http://schema.org/InStock">"""
        p = shoplib.extract_product(html)
        self.assertEqual((p["image"], p["name"], p["availability"]), ("https://cdn/x.jpg", "PLA Mint", "InStock"))

    def test_availability(self):
        self.assertEqual(shoplib.norm_availability("http://schema.org/SoldOut"), "OutOfStock")
        self.assertEqual(shoplib.norm_availability(True), "InStock")
        self.assertEqual(shoplib.stock_label("PreOrder"), "Na objednávku")
        self.assertEqual(shoplib.stock_label(None), "?")


class Naming(unittest.TestCase):
    def test_no_prices(self):
        t = "Filament 3DFOX PETG REFILL antracit 1 kg 1,75 mm jen za 298 Kč ✅ | Filamenty ✅ | 3D FOX shop"
        self.assertEqual(shoplib.clean_title(t), "Filament 3DFOX PETG REFILL antracit 1 kg 1,75 mm")
        self.assertEqual(shoplib.clean_title("PLA červená za 1 299,- Kč"), "PLA červená")
        self.assertEqual(shoplib.derive_color_name(t, "3DFOX", "PETG"), "Antracit")

    def test_brand_cleanup(self):
        self.assertEqual(shoplib.clean_brand("AURAPOL s.r.o."), "AURAPOL")
        self.assertEqual(shoplib.clean_brand("BambuLab original"), "BambuLab")
        self.assertEqual(shoplib.derive_color_name("Filament AURAPOL PETG ARMY Sand Storm 1,75 mm 1 kg", "AURAPOL s.r.o.", "PETG"),
                         "ARMY Sand Storm")
        self.assertEqual(shoplib.derive_color_name("Filament TheFilament PETG ŠEDÁ CLOUD 1,75 mm 1 kg", "Spectrum + The Filament", "PETG"),
                         "Šedá Cloud")
        self.assertEqual(shoplib.derive_color_name("Filament Bambu Lab PLA Basic BLUE GRAY 1,75 mm 1 kg", "BambuLab original", "PLA"),
                         "Basic BLUE GRAY")
        self.assertEqual(shoplib.derive_color_name("Filament AURAPOL PETG ROSE DUST . 1,75 mm 1 kg", "AURAPOL", "PETG"), "Rose Dust")

    def test_h1_beats_og_title(self):
        html = '<meta property="og:title" content="PLA šedá jen za 289 Kč"><h1 itemprop="name"> PLA <b>šedá</b> </h1>'
        self.assertEqual(shoplib.extract_product(html)["name"], "PLA šedá")

    def test_color_name(self):
        self.assertEqual(shoplib.derive_color_name("Filament AURAPOL PLA Cloud Nine 1,75 mm 1 kg", "AURAPOL", "PLA"),
                         "Cloud Nine")
        self.assertEqual(shoplib.derive_color_name("3DPower Basic PETG bílá (white) 1kg | Hubáček 3D", "3DPower", "PETG"),
                         "Basic bílá (white)")
        self.assertEqual(shoplib.derive_color_name("3DPower Basic PETG - Béžová (Beige) - 1kg / 1,75mm :: Hubacek3D",
                                                   "3DPower", "PETG"), "Basic Béžová (Beige)")
        self.assertEqual(shoplib.derive_color_name("PETG Šedá (1,75 mm; 1 kg) | Tiskové struny", "Filament PM", "PETG"), "Šedá")
        self.assertEqual(shoplib.derive_color_name('PLA Extrafill "Lilac" | 1.75 mm', "Fillamentum", "PLA"), "Extrafill Lilac")


if __name__ == "__main__":
    unittest.main()
