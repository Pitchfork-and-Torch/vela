"""path: reject non-positive capacity upper bound (dead rail).

Distinct from inverted rtt_jump/capacity ranges (cook #22), zero handover
interval (#23), zero mobility_loss window (#24), and non-positive contract
duration (#25).
"""
from __future__ import annotations

import unittest

from vela.checker import check
from vela.parser import parse


def _prog(capacity_clause: str) -> str:
    return f"""
lang vela 0.1
use std.path
use std.eval
controller Probe {{
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {{
    RttHop => hold
    Flicker => hold
  }}
  on Loss(k) match k {{
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }}
}}
path LeoFastHO {{
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ {capacity_clause}
  mobility_loss ~ burst p=0.08 window=400ms
}}
contract DualGate vs BBR {{
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  assert mean(goodput) >= 1
  assert terrestrial.goodput >= 77 Mbps
}}
"""


class TestPathZeroCapacity(unittest.TestCase):
    def test_zero_capacity_rejected(self):
        res = check(parse(_prog("uniform 0Mbps 0Mbps"), "zero-cap.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("capacity" in e and "positive" in e for e in res.errors),
            res.errors,
        )

    def test_zero_upper_bound_rejected(self):
        res = check(parse(_prog("uniform 10Mbps 0Mbps"), "zero-hi.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("capacity" in e and "positive" in e for e in res.errors),
            res.errors,
        )

    def test_positive_capacity_ok(self):
        res = check(parse(_prog("uniform 20Mbps 120Mbps"), "ok-cap.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_equal_positive_bounds_ok(self):
        # Equal bounds are not inverted; only non-positive hi is rejected.
        res = check(parse(_prog("uniform 50Mbps 50Mbps"), "eq-cap.vela"))
        self.assertTrue(res.ok, res.errors)


if __name__ == "__main__":
    unittest.main()
