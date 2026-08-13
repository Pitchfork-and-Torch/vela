"""Parser + checker tests for VELA examples."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check
from vela.compile import compile_source
from vela.parser import ParseError, parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


class TestExamplesParse(unittest.TestCase):
    def test_horizon_parses(self):
        src = (EX / "horizon.vela").read_text(encoding="utf-8")
        prog = parse(src, "horizon.vela")
        self.assertEqual(prog.controllers[0].name, "Horizon")
        self.assertIn("PredictiveFreeze", prog.controllers[0].compose)
        self.assertEqual(prog.contracts[0].name, "DualGate")
        self.assertEqual(prog.contracts[0].seeds, [13, 7, 42, 99, 123])

    def test_luff_parses_and_checks(self):
        src = (EX / "luff.vela").read_text(encoding="utf-8")
        prog = parse(src, "luff.vela")
        self.assertEqual(prog.controllers[0].name, "Luff")
        self.assertIn("TrimHold", prog.controllers[0].compose)
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        text, cfg = compile_source(src, "luff.vela")
        self.assertEqual(cfg.name, "Luff")
        self.assertTrue(cfg.trim_hold)
        self.assertTrue(cfg.trim_fill)
        self.assertFalse(cfg.trim_reclaim)

    def test_reach_parses_and_checks(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        prog = parse(src, "reach.vela")
        self.assertEqual(prog.controllers[0].name, "Reach")
        self.assertIn("DualGateGuard", prog.controllers[0].compose)
        self.assertNotIn("SoftFlicker", prog.controllers[0].compose)
        self.assertNotIn("QuietShield", prog.controllers[0].compose)
        self.assertNotIn("TrimHold", prog.controllers[0].compose)
        self.assertNotIn("QuietReach", prog.controllers[0].compose)
        self.assertNotIn("TrimFill", prog.controllers[0].compose)
        self.assertNotIn("HorizonChase", prog.controllers[0].compose)
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        text, cfg = compile_source(src, "reach.vela")
        self.assertEqual(cfg.name, "Reach")
        self.assertFalse(cfg.soft_flicker)
        self.assertFalse(cfg.quiet_shield)
        self.assertFalse(cfg.trim_hold)
        self.assertFalse(cfg.quiet_reach)
        self.assertFalse(cfg.trim_fill)
        self.assertFalse(cfg.trim_reclaim)
        self.assertFalse(cfg.horizon_chase)

    def test_oce_parses(self):
        src = (EX / "leoaware_oce.vela").read_text(encoding="utf-8")
        prog = parse(src, "leoaware_oce.vela")
        self.assertEqual(prog.controllers[0].name, "LeoAwareOCE")
        self.assertIn("OCE", prog.controllers[0].compose)

    def test_horizon_checks(self):
        src = (EX / "horizon.vela").read_text(encoding="utf-8")
        res = check(parse(src, "horizon.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_oce_checks(self):
        src = (EX / "leoaware_oce.vela").read_text(encoding="utf-8")
        res = check(parse(src, "leoaware_oce.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_stale_sample_rejected(self):
        src = """
lang vela 0.1
controller Bad {
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) {
    invalidate min_rtt
    let x = min_rtt
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "bad.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("invalidated" in e for e in res.errors))

    def test_loss_match_must_be_closed(self):
        src = """
lang vela 0.1
controller Bad {
  compose Detect
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
  }
}
"""
        res = check(parse(src, "bad2.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("Unknown" in e for e in res.errors))

    def test_sample_requires_epoch_tag(self):
        src = """
lang vela 0.1
controller Bad {
  compose Detect
  signals:
    epoch: Epoch
    rtt: Sample<ms>
}
"""
        res = check(parse(src, "bad3.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("tagged @ epoch" in e for e in res.errors))

    def test_compile_horizon(self):
        src = (EX / "horizon.vela").read_text(encoding="utf-8")
        text, cfg = compile_source(src, "horizon.vela")
        self.assertIn("HorizonCCA", text)
        self.assertEqual(cfg.name, "Horizon")
        self.assertTrue(cfg.predictive_freeze)

    def test_missing_header(self):
        with self.assertRaises(ParseError):
            parse("controller X { compose Detect }", "x.vela")


if __name__ == "__main__":
    unittest.main()
