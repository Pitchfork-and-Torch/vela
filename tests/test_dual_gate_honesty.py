"""Dual-gate honesty: ACCEPT on gate=fast is not a house win."""
from __future__ import annotations

import unittest

from vela.eval_harness import dual_gate_win, honesty_text
from vela.receipt import gate_cli_line, resolve_eval_rails, eval_gate


class TestDualGateHonestyLabel(unittest.TestCase):
    def test_fast_accept_cli_not_a_win(self):
        line = gate_cli_line("fast", "ACCEPT")
        self.assertIn("not the house gate", line)
        self.assertIn("not a dual-gate win", line)

    def test_house_accept_cli_ok(self):
        line = gate_cli_line("house", "ACCEPT")
        self.assertIn("gate=house", line)
        self.assertNotIn("not a dual-gate win", line)

    def test_honesty_text_fast_flags_non_win(self):
        text = honesty_text("fast", "ACCEPT")
        self.assertIn("gate=fast", text)
        self.assertIn("not a dual-gate win", text)

    def test_dual_gate_win_only_house_accept(self):
        self.assertTrue(dual_gate_win("ACCEPT", "house"))
        self.assertFalse(dual_gate_win("ACCEPT", "fast"))
        self.assertFalse(dual_gate_win("FAIL", "house"))
        self.assertFalse(dual_gate_win("ACCEPT", "named"))

    def test_fast_cannot_mix_seeds_duration(self):
        _, _, _, errs = resolve_eval_rails(
            fast=True, seeds=[13, 7, 42, 99, 123], duration_s=90.0
        )
        self.assertTrue(errs)
        self.assertTrue(any("--fast" in e for e in errs))

    def test_gate_stamped_from_fast_rails(self):
        seeds, dur, scens, errs = resolve_eval_rails(fast=True)
        self.assertEqual(errs, [])
        self.assertEqual(eval_gate(seeds, dur, scens), "fast")


if __name__ == "__main__":
    unittest.main()
