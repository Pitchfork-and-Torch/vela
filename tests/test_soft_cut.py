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


    def test_invalid_factors_do_not_corrupt_cwnd(self):
        before = 12000.0
        # Negatives, zero, NaN, and >1 are not remaining fractions.
        self.assertEqual(compose_soft_cuts([-0.5, 0.0, float("nan"), 1.5]), 1.0)
        self.assertAlmostEqual(apply_composed_cut(before, [-0.5]), before)
        self.assertAlmostEqual(apply_composed_cut(before, [float("nan")]), before)
        self.assertAlmostEqual(apply_composed_cut(before, [1.5]), before)
        # Valid factors still win; junk beside them is ignored.
        self.assertAlmostEqual(
            apply_composed_cut(before, [0.58, -1.0, 1.5, float("nan")]),
            before * 0.58,
        )

if __name__ == "__main__":
    unittest.main()
