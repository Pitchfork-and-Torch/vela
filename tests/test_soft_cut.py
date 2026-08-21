"""Soft cuts compose as min at runtime. SoftFlicker cannot undo 0.58."""
from __future__ import annotations

import unittest

from vela.compose import apply_composed_cut, compose_soft_cuts, soft_cut_mechanisms


class TestSoftCutMin(unittest.TestCase):
    def test_empty_is_identity(self):
        self.assertEqual(compose_soft_cuts([]), 1.0)

    def test_min_is_conservative(self):
        self.assertEqual(compose_soft_cuts([0.58, 0.85]), 0.58)
        self.assertEqual(compose_soft_cuts([0.85, 0.58, 1.0]), 0.58)
        self.assertEqual(compose_soft_cuts([0.85]), 0.85)

    def test_softflicker_cannot_raise_after_house_cut(self):
        before = 12000.0
        house = apply_composed_cut(before, [0.58])
        stacked = apply_composed_cut(before, [0.58, 0.85])
        self.assertAlmostEqual(house, before * 0.58)
        self.assertAlmostEqual(stacked, house)
        self.assertLess(stacked, before * 0.85)

    def test_stdlib_soft_cuts_include_flicker_and_chase(self):
        names = soft_cut_mechanisms()
        self.assertIn("SoftFlicker", names)
        self.assertIn("HorizonChase", names)
        self.assertIn("OCE", names)
        self.assertNotIn("SoftReprobe", names)


if __name__ == "__main__":
    unittest.main()
