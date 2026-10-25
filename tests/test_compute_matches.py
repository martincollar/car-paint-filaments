"""Unit tests for the neon penalty in src/compute_matches.py (no catalogue needed).

    .venv/bin/python -m unittest discover -s tests
"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import compute_matches as cm

LIME = [188, 196, 64]
POOL = [{"slug": "fluo", "rgb": [197, 199, 0], "neon": True},
        {"slug": "plain", "rgb": [156, 175, 16]}]


class NeonPenalty(unittest.TestCase):
    def test_plain_beats_closer_neon(self):
        top = cm.topk(LIME, POOL, k=2)
        self.assertEqual([c["slug"] for c in top], ["plain", "fluo"])
        self.assertLess(top[1]["delta_e"], top[0]["delta_e"])      # shown ΔE stays real

    def test_neon_paint_keeps_plain_ranking(self):
        top = cm.topk([230, 245, 0], POOL, k=2)
        self.assertEqual(top[0]["slug"], "fluo")


if __name__ == "__main__":
    unittest.main()


class FinishPool(unittest.TestCase):
    FILS = [{"slug": "plain", "material": "PLA", "rgb": [200, 30, 30], "regions": ["eu"], "finish": []},
            {"slug": "sparkle", "material": "PLA", "rgb": [190, 30, 30], "regions": ["eu"], "finish": ["glitter"]},
            {"slug": "mattglit", "material": "PLA", "rgb": [190, 30, 30], "regions": ["eu"], "finish": ["glitter", "matt"]}]
    COLORS = [{"name": "Red", "rgb": [190, 30, 30]}]

    def best(self, allowed):
        rec = cm.match_colors(self.COLORS, self.FILS, "eu", frozenset(allowed))[0]
        return [c["slug"] for c in rec["pla"]]

    def test_flagged_filaments_wait_until_allowed(self):
        self.assertEqual(self.best([]), ["plain"])
        self.assertEqual(self.best(["glitter"]), ["sparkle", "plain"])
        self.assertEqual(self.best(["glitter", "matt"]), ["sparkle", "mattglit", "plain"])

    def test_keys(self):
        self.assertEqual(cm.finish_key(frozenset()), "-")
        self.assertEqual(cm.finish_key(frozenset(["matt", "glitter"])), "glitter+matt")
        self.assertEqual(len(cm.all_finish_sets()), 8)

    def test_defaults_from_car_json(self):
        self.assertEqual(cm.allowed_finishes({}), frozenset())
        self.assertEqual(cm.allowed_finishes({"filter_defaults": {"matt": True, "glitter": False}}), frozenset(["matt"]))
