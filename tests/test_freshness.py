"""Freshness law: invalidate is sticky into nested when/if."""
from __future__ import annotations

import unittest

from vela.checker import check
from vela.parser import parse

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(body: str) -> str:
    return f"""
lang vela 0.4
controller Probe {{
  posture observe
  compose Detect + SoftReprobe + IntervalBw
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
{body}
{LOSS}
}}
"""


class TestFreshnessNested(unittest.TestCase):
    def test_nested_when_cannot_read_invalidated_bw(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      when bw.n >= 2 {
        freeze min_rtt for 1.4 * rtt
      }
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "nest-bw.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("invalidated" in e and "bw" in e for e in res.errors),
            res.errors,
        )

    def test_nested_when_cannot_freeze_invalidated_min_rtt(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      when p_ho > 0.5 {
        freeze min_rtt, bw for 1.4 * rtt
      }
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "nest-freeze.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("invalidated" in e and "min_rtt" in e for e in res.errors),
            res.errors,
        )

    def test_enter_after_invalidate_may_read_rtt(self):
        # SoftReprobe explore/fill uses current rtt; invalidate targets min_rtt/bw.
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
        res = check(parse(src, "enter-ok.vela"))
        self.assertTrue(res.ok, res.errors)


if __name__ == "__main__":
    unittest.main()
