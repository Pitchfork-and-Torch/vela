"""Typed loss: observe-only recovery is type-directed."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import (
    check,
    mobility_cut_error,
    typed_loss_error,
    unknown_cut_error,
)
from vela.compile import compile_source
from vela.parser import parse
from vela.types import UNKNOWN_DELAY_RATIO

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

RECONFIG = """
  on Reconfig(e) match e {
    RttHop => hold
    Flicker => hold
  }
"""


def _src(body: str, *, posture: str = "observe") -> str:
    return f"""
lang vela 0.1
controller Probe {{
  posture {posture}
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    delay_ratio: Ratio
{RECONFIG}
{body}
}}
"""


class TestTypedLoss(unittest.TestCase):
    def test_reach_is_typed_loss(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        prog = parse(src, "reach.vela")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.typed_loss)
        self.assertTrue(res.passthrough)
        _, cfg = compile_source(src, "reach.vela")
        self.assertTrue(cfg.typed_loss)
        self.assertTrue(cfg.passthrough)

    def test_observe_examples_are_typed_loss(self):
        for name in ("equinox.vela", "horizon.vela", "ascent.vela"):
            src = (EX / name).read_text(encoding="utf-8")
            res = check(parse(src, name))
            self.assertTrue(res.ok, (name, res.errors))
            self.assertTrue(res.typed_loss, name)
            self.assertTrue(res.passthrough, name)

    def test_observe_bare_loss_is_error(self):
        src = _src(
            """
  on Loss(k) {
    cut(0.72)
  }
"""
        )
        res = check(parse(src, "bare-loss.vela"))
        self.assertFalse(res.ok)
        self.assertIn(typed_loss_error("Probe"), res.errors)
        self.assertFalse(res.typed_loss)
        self.assertFalse(res.passthrough)

    def test_observe_mobility_cut_is_error(self):
        src = _src(
            """
  on Loss(k) match k {
    Mobility => cut(0.72)
    Congestive => cut(0.72)
    Unknown => hold
  }
"""
        )
        res = check(parse(src, "mob-cut.vela"))
        self.assertFalse(res.ok)
        self.assertIn(mobility_cut_error("Probe"), res.errors)
        self.assertTrue(res.typed_loss)

    def test_observe_unknown_cut_without_delay_is_error(self):
        src = _src(
            """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => cut(0.72)
  }
"""
        )
        res = check(parse(src, "unk-cut.vela"))
        self.assertFalse(res.ok)
        self.assertIn(unknown_cut_error("Probe"), res.errors)
        self.assertTrue(res.typed_loss)

    def test_observe_unknown_weak_delay_is_error(self):
        src = _src(
            """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => require delay_ratio > 1.0 then cut(0.72) else hold
  }
"""
        )
        res = check(parse(src, "unk-weak.vela"))
        self.assertFalse(res.ok)
        self.assertIn(unknown_cut_error("Probe"), res.errors)

    def test_observe_unknown_else_cut_is_error(self):
        src = _src(
            """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => require delay_ratio > 1.35 then hold else cut(0.72)
  }
"""
        )
        res = check(parse(src, "unk-else.vela"))
        self.assertFalse(res.ok)
        self.assertIn(unknown_cut_error("Probe"), res.errors)

    def test_observe_kinded_loss_with_delay_proof_ok(self):
        src = _src(
            f"""
  on Loss(k) match k {{
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => require delay_ratio > {UNKNOWN_DELAY_RATIO} then cut(0.72) else hold
  }}
"""
        )
        res = check(parse(src, "kinded-loss.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.typed_loss)
        self.assertTrue(res.observe_only)
        self.assertTrue(res.passthrough)
        _, cfg = compile_source(src, "kinded-loss.vela")
        self.assertTrue(cfg.typed_loss)

    def test_observe_unknown_hold_ok(self):
        src = _src(
            """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }
"""
        )
        res = check(parse(src, "unk-hold.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.typed_loss)
        self.assertTrue(res.passthrough)

    def test_review_may_keep_bare_loss(self):
        src = _src(
            """
  on Loss(k) {
    cut(0.72)
  }
""",
            posture="review",
        )
        res = check(parse(src, "review-bare-loss.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.typed_loss)
        self.assertFalse(res.passthrough)

    def test_review_may_cut_mobility(self):
        src = _src(
            """
  on Loss(k) match k {
    Mobility => cut(0.72)
    Congestive => cut(0.72)
    Unknown => cut(0.72)
  }
""",
            posture="review",
        )
        res = check(parse(src, "review-mob-cut.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.typed_loss)
        self.assertFalse(res.observe_only)

    def test_ir_does_not_stamp_typed_loss_on_bare(self):
        src = _src(
            """
  on Loss(k) {
    cut(0.72)
  }
""",
            posture="review",
        )
        _, cfg = compile_source(src, "ir-bare.vela")
        self.assertFalse(cfg.typed_loss)

    def test_kinded_observe_still_rejects_closed_write(self):
        src = """
lang vela 0.1
controller Probe {
  compose Detect + SoftReprobe + QuietReach
  signals:
    epoch: Epoch
    delay_ratio: Ratio
  on Reconfig(e) match e {
    RttHop => hold
    Flicker => hold
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "loss-sneak.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(res.typed_loss)
        self.assertFalse(res.observe_only)
        self.assertFalse(res.passthrough)


if __name__ == "__main__":
    unittest.main()
