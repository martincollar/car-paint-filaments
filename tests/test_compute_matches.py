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
