"""path realism: inverted uniform ranges + zero mobility window.

Re-lands the spirit of closed cooks #22 and #24 on current main.
Distinct from #26 (non-positive capacity upper) and steward #27 (cadence).
Equal positive bounds remain valid.
"""
from __future__ import annotations

import unittest

from vela.checker import check
from vela.parser import parse
from vela.path import (
    path_inverted_range_error,
    path_zero_mobility_window_error,
)


def _prog(**fields: str) -> str:
    body = {
        "handover": "every 12s jitter 4s",
        "rtt_jump": "uniform 20ms 90ms",
        "capacity": "uniform 20Mbps 120Mbps",
        "mobility_loss": "burst p=0.08 window=400ms",
    }
    body.update(fields)
    path_lines = "\n".join(f"  {k} ~ {v}" for k, v in body.items())
    return f"""
lang vela 0.1
use std.path
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
{path_lines}
}}
"""


class TestPathRealismRails(unittest.TestCase):
    def test_inverted_rtt_jump_rejected(self):
        res = check(parse(_prog(rtt_jump="uniform 90ms 20ms"), "inv-rtt.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_inverted_range_error("LeoFastHO", "rtt_jump"), res.errors)

    def test_inverted_capacity_rejected(self):
        res = check(parse(_prog(capacity="uniform 120Mbps 20Mbps"), "inv-cap.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_inverted_range_error("LeoFastHO", "capacity"), res.errors)

    def test_equal_bounds_ok(self):
        res = check(
            parse(
                _prog(
                    rtt_jump="uniform 40ms 40ms",
                    capacity="uniform 50Mbps 50Mbps",
                ),
                "eq.vela",
            )
        )
        self.assertTrue(res.ok, res.errors)

    def test_zero_mobility_window_rejected(self):
        res = check(
            parse(_prog(mobility_loss="burst p=0.08 window=0ms"), "zero-mob.vela")
        )
        self.assertFalse(res.ok)
        self.assertIn(path_zero_mobility_window_error("LeoFastHO"), res.errors)

    def test_house_rails_still_ok(self):
        res = check(parse(_prog(), "house.vela"))
        self.assertTrue(res.ok, res.errors)


if __name__ == "__main__":
    unittest.main()
