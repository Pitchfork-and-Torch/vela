"""Observe posture: Reach is checkable without closed-write."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check, closed_write_error
from vela.compile import compile_source
from vela.parser import ParseError, parse
from vela.types import CLOSED_WRITE_OPERATORS, is_observe_only, review_writes_in

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(body: str) -> str:
    return f"""
lang vela 0.1
controller Probe {{
{body}
{LOSS}
}}
"""


class TestObservePosture(unittest.TestCase):
    def test_reach_is_observe_only(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        prog = parse(src, "reach.vela")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.posture, "observe")
        self.assertTrue(res.observe_only)
        self.assertEqual(res.closed_writes, [])
        _, cfg = compile_source(src, "reach.vela")
        self.assertTrue(cfg.observe_only)
        self.assertFalse(cfg.horizon_chase)
        self.assertFalse(cfg.quiet_reach)
        self.assertFalse(cfg.trim_hold)
        self.assertFalse(cfg.oce_legacy)

    def test_equinox_and_horizon_are_observe_only(self):
        for name in ("equinox.vela", "horizon.vela", "ascent.vela"):
            src = (EX / name).read_text(encoding="utf-8")
            res = check(parse(src, name))
            self.assertTrue(res.ok, (name, res.errors))
            self.assertTrue(res.observe_only, name)
            self.assertEqual(res.posture, "observe", name)

    def test_default_posture_is_observe(self):
        src = _src(
            """
  compose Detect + SoftReprobe + IntervalBw
  signals:
    epoch: Epoch
"""
        )
        prog = parse(src, "default.vela")
        self.assertEqual(prog.controllers[0].posture, "observe")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.observe_only)

    def test_quiet_reach_on_observe_is_error(self):
        src = _src(
            """
  posture observe
  compose Detect + SoftReprobe + QuietReach
  signals:
    epoch: Epoch
"""
        )
        res = check(parse(src, "sneak.vela"))
        self.assertFalse(res.ok)
        self.assertIn(closed_write_error("Probe", ["QuietReach"]), res.errors)
        self.assertFalse(res.observe_only)

    def test_each_closed_write_needs_review(self):
        for name in sorted(CLOSED_WRITE_OPERATORS):
            src = _src(
                f"""
  compose Detect + {name}
  signals:
    epoch: Epoch
"""
            )
            res = check(parse(src, f"{name}.vela"))
            self.assertFalse(res.ok, name)
            self.assertTrue(any("posture review" in e for e in res.errors), name)

    def test_oce_legacy_write_needs_review(self):
        src = _src(
            """
  compose Detect + SoftReprobe + OCE
  signals:
    epoch: Epoch
"""
        )
        res = check(parse(src, "oce.vela"))
        self.assertFalse(res.ok)
        self.assertIn(closed_write_error("Probe", ["OCE"]), res.errors)

    def test_review_allows_closed_write_with_warning(self):
        src = _src(
            """
  posture review
  compose Detect + SoftReprobe + QuietReach
  signals:
    epoch: Epoch
"""
        )
        prog = parse(src, "review.vela")
        self.assertEqual(prog.controllers[0].posture, "review")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.observe_only)
        self.assertEqual(res.closed_writes, ["QuietReach"])
        self.assertTrue(any("ablation only" in w for w in res.warnings))
        _, cfg = compile_source(src, "review.vela")
        self.assertEqual(cfg.posture, "review")
        self.assertTrue(cfg.quiet_reach)
        self.assertFalse(cfg.observe_only)

    def test_review_examples_check(self):
        for name in ("luff.vela", "leoaware_oce.vela", "reach_softflicker.vela"):
            src = (EX / name).read_text(encoding="utf-8")
            prog = parse(src, name)
            self.assertEqual(prog.controllers[0].posture, "review", name)
            res = check(prog)
            self.assertTrue(res.ok, (name, res.errors))
            self.assertFalse(res.observe_only, name)
            self.assertTrue(res.closed_writes, name)

    def test_observe_compile_clears_write_flags(self):
        src = _src(
            """
  posture observe
  compose Detect + SoftReprobe + IntervalBw
  signals:
    epoch: Epoch
"""
        )
        _, cfg = compile_source(src, "clear.vela")
        self.assertTrue(cfg.observe_only)
        self.assertFalse(cfg.horizon_chase)
        self.assertFalse(cfg.trim_fill)
        self.assertFalse(cfg.quiet_shield)

    def test_view_cannot_sneak_closed_write(self):
        src = """
lang vela 0.3
controller Base {
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
view Sneak of Base {
  compose Detect + SoftReprobe + QuietReach
}
"""
        res = check(parse(src, "view-sneak.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("view Sneak" in e and "QuietReach" in e for e in res.errors))

    def test_unknown_posture_is_parse_error(self):
        src = _src(
            """
  posture write
  compose Detect
"""
        )
        with self.assertRaises(ParseError) as ctx:
            parse(src, "bad-posture.vela")
        self.assertIn("posture must be observe | review", str(ctx.exception))

    def test_review_writes_helper(self):
        self.assertEqual(review_writes_in(["Detect", "QuietReach", "OCE"]), ["QuietReach", "OCE"])
        self.assertTrue(is_observe_only(["Detect", "SoftReprobe", "IntervalBw"]))
        self.assertFalse(is_observe_only(["Detect", "HorizonChase"]))


if __name__ == "__main__":
    unittest.main()
