"""Observe posture: Reach is checkable without closed-write."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import (
    check,
    closed_write_error,
    cruise_write_error,
    house_cut_error,
    typed_reconfig_error,
)
from vela.compile import compile_source
from vela.parser import ParseError, parse
from vela.types import CLOSED_WRITE_OPERATORS, HOUSE_ENDPOINT_CUT, is_observe_only, review_writes_in

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
        self.assertTrue(res.typed_reconfig)
        self.assertTrue(res.typed_loss)
        self.assertTrue(res.passthrough)
        self.assertEqual(res.closed_writes, [])
        _, cfg = compile_source(src, "reach.vela")
        self.assertTrue(cfg.observe_only)
        self.assertTrue(cfg.passthrough)
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
            self.assertTrue(res.typed_reconfig, name)
            self.assertTrue(res.typed_loss, name)
            self.assertTrue(res.passthrough, name)

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
        self.assertFalse(res.passthrough)

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

    def test_observe_bare_reconfig_is_error(self):
        src = _src(
            """
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) {
    invalidate min_rtt, bw
    enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
  }
"""
        )
        res = check(parse(src, "bare-re.vela"))
        self.assertFalse(res.ok)
        self.assertIn(typed_reconfig_error("Probe"), res.errors)
        self.assertFalse(res.typed_reconfig)

    def test_observe_reconfig_must_name_flicker(self):
        src = _src(
            """
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
  }
"""
        )
        res = check(parse(src, "hop-only.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("Flicker" in e for e in res.errors))
        self.assertFalse(res.typed_reconfig)

    def test_observe_softflicker_cut_is_error(self):
        src = _src(
            """
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
    Flicker => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.85, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
  }
"""
        )
        res = check(parse(src, "soft-cut.vela"))
        self.assertFalse(res.ok)
        self.assertIn(house_cut_error("Probe", 0.85), res.errors)
        self.assertTrue(res.typed_reconfig)

    def test_observe_kinded_reconfig_with_house_cut_ok(self):
        src = _src(
            f"""
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {{
    RttHop => {{
      invalidate min_rtt, bw
      enter Reprobe(cut: {HOUSE_ENDPOINT_CUT}, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }}
    Flicker => {{
      invalidate min_rtt, bw
      enter Reprobe(cut: {HOUSE_ENDPOINT_CUT}, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }}
  }}
"""
        )
        res = check(parse(src, "kinded.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.typed_reconfig)
        self.assertTrue(res.typed_loss)
        self.assertTrue(res.observe_only)
        self.assertTrue(res.passthrough)
        self.assertEqual(res.closed_writes, [])

    def test_review_may_keep_bare_reconfig(self):
        src = _src(
            """
  posture review
  compose Detect + SoftReprobe + SoftFlicker
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) {
    invalidate min_rtt, bw
    enter Reprobe(cut: 0.85, explore: 1.15 * rtt, fill: 1.85 * rtt)
  }
"""
        )
        res = check(parse(src, "review-bare.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.typed_reconfig)
        self.assertFalse(res.observe_only)
        self.assertEqual(res.closed_writes, ["SoftFlicker"])

    def test_kinded_observe_still_rejects_closed_write(self):
        src = _src(
            """
  compose Detect + SoftReprobe + QuietReach
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => hold
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "kinded-sneak.vela"))
        self.assertFalse(res.ok)
        self.assertIn(closed_write_error("Probe", ["QuietReach"]), res.errors)
        self.assertTrue(res.typed_reconfig)
        self.assertFalse(res.observe_only)

    def test_observe_pace_assign_is_cruise_write(self):
        src = _src(
            """
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    bw: Interval<bps> @ epoch
  when bw.n >= 2 {
    pace = bw.mid
  }
"""
        )
        res = check(parse(src, "cruise-pace.vela"))
        self.assertFalse(res.ok)
        self.assertIn(cruise_write_error("Probe", "pace ="), res.errors)
        self.assertFalse(res.passthrough)
        self.assertTrue(res.observe_only)

    def test_observe_chase_is_cruise_write(self):
        src = _src(
            """
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
  every ack {
    chase delivery toward 1
  }
"""
        )
        res = check(parse(src, "cruise-chase.vela"))
        self.assertFalse(res.ok)
        self.assertIn(cruise_write_error("Probe", "chase"), res.errors)
        self.assertFalse(res.passthrough)

    def test_observe_cut_on_when_is_cruise_write(self):
        src = _src(
            """
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
  when p_ho > 0.5 {
    cut(0.58)
  }
"""
        )
        res = check(parse(src, "cruise-cut.vela"))
        self.assertFalse(res.ok)
        self.assertIn(cruise_write_error("Probe", "cut"), res.errors)

    def test_observe_freeze_is_not_a_cruise_write(self):
        src = _src(
            """
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => hold
    Flicker => hold
  }
  when p_ho > 0.55 {
    freeze min_rtt, bw for 1.4 * rtt
  }
"""
        )
        res = check(parse(src, "freeze-ok.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.passthrough)
        self.assertTrue(res.observe_only)

    def test_review_may_keep_cruise_write(self):
        src = _src(
            """
  posture review
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    bw: Interval<bps> @ epoch
  when bw.n >= 2 {
    pace = bw.mid
  }
"""
        )
        res = check(parse(src, "review-cruise.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.passthrough)
        self.assertFalse(res.observe_only)

    def test_review_writes_helper(self):
        self.assertEqual(review_writes_in(["Detect", "QuietReach", "OCE"]), ["QuietReach", "OCE"])
        self.assertTrue(is_observe_only(["Detect", "SoftReprobe", "IntervalBw"]))
        self.assertFalse(is_observe_only(["Detect", "HorizonChase"]))


if __name__ == "__main__":
    unittest.main()
