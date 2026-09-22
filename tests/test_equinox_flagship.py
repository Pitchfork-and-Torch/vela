"""Equinox/CONSTELLATION align with Reach as observe-only flagship."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check
from vela.parser import parse


ROOT = Path(__file__).resolve().parents[1]


class TestEquinoxFlagshipAlign(unittest.TestCase):
    def test_equinox_and_reach_both_observe_only(self):
        for name in ("reach.vela", "equinox.vela"):
            src = (ROOT / "examples" / name).read_text(encoding="utf-8")
            res = check(parse(src, name))
            self.assertTrue(res.ok, (name, res.errors))
            self.assertTrue(res.observe_only, name)
            self.assertEqual(res.posture, "observe", name)

    def test_docs_name_reach_flagship(self):
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        constel = (ROOT / "docs" / "CONSTELLATION.md").read_text(encoding="utf-8")
        self.assertIn("reach.vela", equinox)
        self.assertIn("Flagship", equinox)
        self.assertIn("reach.vela", constel)
        src = (ROOT / "examples" / "equinox.vela").read_text(encoding="utf-8")
        self.assertIn("reach.vela", src)


if __name__ == "__main__":
    unittest.main()
