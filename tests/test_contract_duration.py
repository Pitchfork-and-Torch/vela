"""Contract duration must be positive  -  zero used to check ok and eval empty."""
from __future__ import annotations

import unittest

from vela.checker import check
from vela.parser import parse


def _prog(duration_clause: str) -> str:
    return f"""
lang vela 0.1
use std.path
use std.eval
controller Probe {{
  posture observe
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
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}}
contract DualGate vs BBR {{
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho {duration_clause}
  assert mean(goodput) >= 1
  assert terrestrial.goodput >= 77 Mbps
}}
"""


class TestContractDuration(unittest.TestCase):
    def test_zero_duration_rejected(self):
        res = check(parse(_prog("duration 0s"), "zero-dur.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("duration must be positive" in e for e in res.errors),
            res.errors,
        )

    def test_positive_duration_ok(self):
        res = check(parse(_prog("duration 90s"), "ok-dur.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_tiny_positive_duration_ok(self):
        res = check(parse(_prog("duration 1ms"), "tiny-dur.vela"))
        self.assertTrue(res.ok, res.errors)


if __name__ == "__main__":
    unittest.main()
