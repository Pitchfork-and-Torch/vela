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
        self.assertEqual(prog.controllers[0].posture, "review")
        text, cfg = compile_source(src, "luff.vela")
        self.assertEqual(cfg.name, "Luff")
        self.assertEqual(cfg.posture, "review")
        self.assertFalse(cfg.observe_only)
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
        self.assertEqual(prog.controllers[0].posture, "observe")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.observe_only)
        self.assertTrue(res.typed_reconfig)
        self.assertTrue(res.passthrough)
        self.assertEqual(res.posture, "observe")
        self.assertEqual(res.closed_writes, [])
        text, cfg = compile_source(src, "reach.vela")
        self.assertEqual(cfg.name, "Reach")
        self.assertEqual(cfg.posture, "observe")
        self.assertTrue(cfg.observe_only)
        self.assertTrue(cfg.passthrough)
        self.assertFalse(cfg.soft_flicker)
        self.assertFalse(cfg.quiet_shield)
        self.assertFalse(cfg.trim_hold)
        self.assertFalse(cfg.quiet_reach)
        self.assertFalse(cfg.trim_fill)
        self.assertFalse(cfg.trim_reclaim)
        self.assertFalse(cfg.horizon_chase)
        self.assertFalse(cfg.oce_legacy)

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
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt
      let x = min_rtt
    }
    Flicker => hold
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

    def test_examples_need_no_compose_combinators(self):
        for name in (
            "horizon.vela",
            "reach.vela",
            "luff.vela",
            "leoaware_oce.vela",
            "equinox.vela",
            "ascent.vela",
        ):
            src = (EX / name).read_text(encoding="utf-8")
            prog = parse(src, name)
            for c in prog.controllers:
                self.assertIsNone(c.cuts_compose, name)
                self.assertIsNone(c.growth_compose, name)
            res = check(prog)
            self.assertTrue(res.ok, (name, res.errors))


class TestComposeCutsAndGrowth(unittest.TestCase):
    def test_two_hard_epoch_cuts_ok_with_min(self):
        src = """
lang vela 0.1
controller DualCut {
  compose SoftReprobe + SoftReprobe
  compose cuts = min
}
"""
        prog = parse(src, "dual-cut-min.vela")
        c = prog.controllers[0]
        self.assertEqual(c.cuts_compose, "min")
        self.assertIsNone(c.growth_compose)
        self.assertEqual(c.compose, ["SoftReprobe", "SoftReprobe"])
        res = check(prog)
        self.assertTrue(res.ok, res.errors)

    def test_two_hard_epoch_cuts_error_without_clause(self):
        src = """
lang vela 0.1
controller DualCut {
  compose SoftReprobe + SoftReprobe
}
"""
        prog = parse(src, "dual-cut.vela")
        self.assertIsNone(prog.controllers[0].cuts_compose)
        res = check(prog)
        self.assertFalse(res.ok)
        self.assertTrue(any("compose cuts = min" in e for e in res.errors))

    def test_trailing_compose_cuts_after_list(self):
        src = """
lang vela 0.1
controller DualCut {
  compose SoftReprobe + SoftReprobe compose cuts = min
}
"""
        prog = parse(src, "dual-cut-trail.vela")
        self.assertEqual(prog.controllers[0].cuts_compose, "min")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)

    def test_parse_compose_growth_max(self):
        src = """
lang vela 0.1
controller Grow {
  posture review
  compose OCE + HorizonChase
  compose growth = max
}
"""
        prog = parse(src, "growth-max.vela")
        c = prog.controllers[0]
        self.assertEqual(c.growth_compose, "max")
        self.assertIsNone(c.cuts_compose)
        self.assertEqual(c.compose, ["OCE", "HorizonChase"])
        res = check(prog)
        self.assertTrue(res.ok, res.errors)

    def test_two_cwnd_raisers_error_without_growth(self):
        src = """
lang vela 0.1
controller Grow {
  posture review
  compose OCE + HorizonChase
}
"""
        res = check(parse(src, "growth-bare.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("compose growth" in e for e in res.errors))

    def test_compose_growth_min_and_sum(self):
        for val in ("min", "sum"):
            src = f"""
lang vela 0.1
controller Grow {{
  posture review
  compose TrimFill + QuietReach
  compose growth = {val}
}}
"""
            prog = parse(src, f"growth-{val}.vela")
            self.assertEqual(prog.controllers[0].growth_compose, val)
            res = check(prog)
            self.assertTrue(res.ok, (val, res.errors))

    def test_own_line_and_trailing_combinators_together(self):
        src = """
lang vela 0.1
controller Mix {
  posture review
  compose SoftReprobe + SoftReprobe + OCE + TrimReclaim compose cuts = min
  compose growth = min
}
"""
        prog = parse(src, "mix.vela")
        c = prog.controllers[0]
        self.assertEqual(c.cuts_compose, "min")
        self.assertEqual(c.growth_compose, "min")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)

    def test_cuts_rejects_non_min(self):
        src = """
lang vela 0.1
controller Bad {
  compose SoftReprobe
  compose cuts = max
}
"""
        with self.assertRaises(ParseError) as ctx:
            parse(src, "bad-cuts.vela")
        self.assertIn("compose cuts must be min", str(ctx.exception))

    def test_growth_rejects_unknown_value(self):
        src = """
lang vela 0.1
controller Bad {
  compose OCE
  compose growth = avg
}
"""
        with self.assertRaises(ParseError) as ctx:
            parse(src, "bad-growth.vela")
        self.assertIn("compose growth must be min | max | sum", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
