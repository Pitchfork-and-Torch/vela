"""Hybrid automata: on is a jump, when/every are flows."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import (
    check,
    hybrid_jump_in_flow_error,
    hybrid_tick_error,
    hybrid_unknown_mode_error,
)
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(body: str, *, posture: str = "review") -> str:
    return f"""
lang vela 0.4
controller Probe {{
  posture {posture}
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
{body}
{LOSS}
}}
"""


class TestHybridAutomata(unittest.TestCase):
    def test_flagship_examples_are_hybrid(self):
        for name in (
            "reach.vela",
            "fair.vela",
            "equinox.vela",
            "horizon.vela",
            "ascent.vela",
            "luff.vela",
            "leoaware_oce.vela",
        ):
            src = (EX / name).read_text(encoding="utf-8")
            res = check(parse(src, name))
            self.assertTrue(res.ok, (name, res.errors))
            self.assertTrue(res.hybrid, name)

    def test_enter_in_when_is_jump_in_flow(self):
        src = _src(
            """
  when p_ho > 0.5 {
    enter Reprobe(cut: 0.58)
  }
"""
        )
        res = check(parse(src, "enter-when.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertIn(
            hybrid_jump_in_flow_error("Probe", "enter Reprobe", "when"),
            res.errors,
        )

    def test_invalidate_in_every_is_jump_in_flow(self):
        src = _src(
            """
  every ack {
    invalidate min_rtt, bw
  }
"""
        )
        res = check(parse(src, "inv-every.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertIn(
            hybrid_jump_in_flow_error("Probe", "invalidate", "every"),
            res.errors,
        )

    def test_cut_in_when_is_jump_in_flow(self):
        src = _src(
            """
  when delay_ratio > 1.35 {
    cut(0.72)
  }
"""
        )
        res = check(parse(src, "cut-when.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertIn(
            hybrid_jump_in_flow_error("Probe", "cut", "when"),
            res.errors,
        )

    def test_enter_in_on_is_legal_jump(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58)
    }
    Flicker => hold
  }
""",
            posture="observe",
        )
        res = check(parse(src, "enter-on.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hybrid)

    def test_guarded_enter_inside_on_is_still_a_jump(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      when p_ho > 0.5 {
        enter Reprobe(cut: 0.58)
      }
    }
    Flicker => hold
  }
""",
            posture="observe",
        )
        res = check(parse(src, "guarded-on.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hybrid)

    def test_unknown_enter_mode(self):
        src = _src(
            """
  on Reconfig(e) {
    enter Cruise
  }
"""
        )
        res = check(parse(src, "mode.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertIn(hybrid_unknown_mode_error("Probe", "Cruise"), res.errors)

    def test_every_unknown_tick(self):
        src = _src(
            """
  every rtt {
    freeze bw
  }
"""
        )
        res = check(parse(src, "tick.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertIn(hybrid_tick_error("Probe", "rtt"), res.errors)

    def test_freeze_in_when_is_a_flow(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => hold
    Flicker => hold
  }
  when p_ho > 0.55 {
    freeze min_rtt, bw for 1.4 * rtt
  }
""",
            posture="observe",
        )
        res = check(parse(src, "flow.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hybrid)
        self.assertTrue(res.passthrough)

    def test_chase_in_every_ack_is_a_flow(self):
        src = _src(
            """
  every ack {
    chase delivery toward 1
  }
"""
        )
        res = check(parse(src, "chase-flow.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hybrid)


    def test_cut_in_every_epoch_is_jump_in_flow(self):
        src = _src(
            """
  every epoch {
    cut(0.58)
  }
"""
        )
        res = check(parse(src, "cut-epoch.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertIn(
            hybrid_jump_in_flow_error("Probe", "cut", "every"),
            res.errors,
        )

    def test_enter_in_every_epoch_is_jump_in_flow(self):
        src = _src(
            """
  every epoch {
    enter Reprobe(cut: 0.58)
  }
"""
        )
        res = check(parse(src, "enter-epoch.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertIn(
            hybrid_jump_in_flow_error("Probe", "enter Reprobe", "every"),
            res.errors,
        )


if __name__ == "__main__":
    unittest.main()
