"""Affine samples: use-once per block, e+1 is prior after Reprobe."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import (
    affine_epoch_error,
    affine_mix_error,
    affine_reuse_error,
    check,
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


def _src(body: str, *, posture: str = "observe") -> str:
    return f"""
lang vela 0.4
controller Probe {{
  posture {posture}
  compose Detect + SoftReprobe + IntervalBw
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
    delay_ratio: Ratio
{body}
{LOSS}
}}
"""


class TestAffineSamples(unittest.TestCase):
    def test_flagship_examples_are_affine(self):
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
            self.assertTrue(res.affine, name)

    def test_one_statement_may_mention_rtt_twice(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "one-use.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.affine)

    def test_second_read_in_block_is_error(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      let a = rtt
      let b = rtt
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "reuse.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.affine)
        self.assertIn(affine_reuse_error("Probe", "rtt"), res.errors)

    def test_let_bind_allows_copy(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      let r = rtt
      enter Reprobe(cut: 0.58, explore: 1.15 * r, fill: 1.85 * r)
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "let-copy.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.affine)

    def test_after_reprobe_current_sample_is_e1(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58)
      let x = rtt
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "eplus1.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.affine)
        self.assertIn(affine_epoch_error("Probe", "rtt"), res.errors)

    def test_after_reprobe_prior_is_legal(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58)
      let x = prior.rtt
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "prior-ok.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.affine)

    def test_mix_current_and_prior_is_error(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: rtt + prior.rtt)
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "mix.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.affine)
        self.assertIn(affine_mix_error("Probe", "rtt"), res.errors)

    def test_branches_may_each_use_once(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      require delay_ratio > 1.35 then {
        let a = rtt
      } else {
        let b = rtt
      }
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "branch.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.affine)

    def test_use_after_branch_that_consumed_is_error(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      require delay_ratio > 1.35 then {
        let a = rtt
      } else {
        hold
      }
      let b = rtt
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "join.vela"))
        self.assertFalse(res.ok)
        self.assertIn(affine_reuse_error("Probe", "rtt"), res.errors)

    def test_guard_does_not_consume(self):
        src = _src(
            """
  when rtt > 20ms {
    freeze min_rtt, bw for 1.4 * rtt
  }
  on Reconfig(e) match e {
    RttHop => hold
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "guard.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.affine)

    def test_interval_n_does_not_consume_point(self):
        src = _src(
            """
  when bw.n >= 2 {
    pace = bw.mid
  }
  on Reconfig(e) match e {
    RttHop => hold
    Flicker => hold
  }
""",
            posture="review",
        )
        res = check(parse(src, "n-attr.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.affine)


class TestIntegratorEvery(unittest.TestCase):
    def test_every_scale_is_integrator(self):
        src = _src(
            """
  every ack {
    pace *= 0.94
  }
  on Reconfig(e) match e {
    RttHop => hold
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "every-int.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("integrator" in e and "every" in e for e in res.errors))

    def test_integrate_every_opts_in(self):
        src = _src(
            """
  integrate every ack {
    pace *= 0.94
  }
  on Reconfig(e) match e {
    RttHop => hold
    Flicker => hold
  }
""",
            posture="review",
        )
        res = check(parse(src, "integrate-every.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("integrate every" in w for w in res.warnings))

    def test_nested_when_in_on_is_integrator(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      when p_ho > 0.35 {
        pace *= 0.94
      }
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "nested-when.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("integrator" in e for e in res.errors))


if __name__ == "__main__":
    unittest.main()
