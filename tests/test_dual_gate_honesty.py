"""ACCEPT on gate=fast must not read as a house dual-gate win."""
from __future__ import annotations

import unittest

from vela.eval_harness import _summarize, honesty_text
from vela.ir import VelaConfig
from vela.receipt import gate_cli_line
from vela.types import dual_gate_claim


HOUSE = [13, 7, 42, 99, 123]


def _rows(scenario: str, cca: str, gp: float, p95: float, seeds=None):
    return [
        {
            "scenario": scenario,
            "seed": seed,
            "cca": cca,
            "goodput_mbps": gp,
            "p95_rtt_ms": p95,
        }
        for seed in (seeds if seeds is not None else HOUSE)
    ]


class TestDualGateHonesty(unittest.TestCase):
    def test_helper_false_on_fast_accept(self):
        self.assertFalse(dual_gate_claim("fast", "ACCEPT"))
        self.assertFalse(dual_gate_claim("fast", "FAIL"))
        self.assertTrue(dual_gate_claim("house", "ACCEPT"))
        self.assertFalse(dual_gate_claim("house", "FAIL"))

    def test_fast_accept_summary_stamps_false_claim(self):
        # Fast rails: 2 seeds, 45s -> gate=fast even if means ACCEPT.
        seeds = [13, 7]
        cfg = VelaConfig(name="Reach", seeds=list(seeds), duration_s=45.0)
        rows = (
            _rows("leo_fast_ho", "Reach", 80.0, 120.0, seeds)
            + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0, seeds)
            + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0, seeds)
            + _rows("terrestrial", "Reach", 78.0, 40.0, seeds)
        )
        summary = _summarize(rows, cfg, duration_s=45.0)
        self.assertEqual(summary["gate"], "fast")
        self.assertEqual(summary["verdict"], "ACCEPT")
        self.assertFalse(summary["dual_gate_claim"])
        self.assertIn("dual_gate_claim=false", summary["honesty"])
        self.assertIn("not a dual-gate win", gate_cli_line("fast", "ACCEPT"))

    def test_house_accept_may_claim(self):
        cfg = VelaConfig(name="Reach", seeds=list(HOUSE), duration_s=90.0)
        rows = (
            _rows("leo_fast_ho", "Reach", 80.0, 120.0)
            + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0)
            + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0)
            + _rows("terrestrial", "Reach", 78.0, 40.0)
        )
        summary = _summarize(rows, cfg, duration_s=90.0)
        self.assertEqual(summary["gate"], "house")
        self.assertEqual(summary["verdict"], "ACCEPT")
        self.assertTrue(summary["dual_gate_claim"])
        self.assertIn("dual_gate_claim=true", summary["honesty"])

    def test_honesty_text_mentions_claim_bit(self):
        self.assertIn("dual_gate_claim=false", honesty_text("fast", "ACCEPT"))
        self.assertIn("dual_gate_claim=true", honesty_text("house", "ACCEPT"))


if __name__ == "__main__":
    unittest.main()


class TestCliDumpsClaim(unittest.TestCase):
    def test_cli_lists_dual_gate_claim_key(self):
        src = (Path(__file__).resolve().parents[1] / "vela" / "cli.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"dual_gate_claim"', src)


if __name__ == "__main__":
    unittest.main()
