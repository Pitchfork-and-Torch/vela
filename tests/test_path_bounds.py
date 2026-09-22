"""Path law: reject impossible Starlink-class rails (bounds)."""
from __future__ import annotations

import unittest

from vela.checker import check
from vela.parser import parse
from vela.path import (
    path_inverted_bounds_error,
    path_jitter_exceeds_error,
    path_zero_capacity_error,
    path_zero_handover_error,
    path_zero_mobility_window_error,
)


def _prog(path_body: str) -> str:
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
{path_body}
"""


class TestPathBounds(unittest.TestCase):
    def test_inverted_capacity_rejected(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  capacity ~ uniform 120Mbps 20Mbps
}
"""
        )
        res = check(parse(src, "inv-cap.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_inverted_bounds_error("LeoFastHO", "capacity"), res.errors)

    def test_inverted_rtt_jump_rejected(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 90ms 20ms
}
"""
        )
        res = check(parse(src, "inv-rtt.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_inverted_bounds_error("LeoFastHO", "rtt_jump"), res.errors)

    def test_zero_capacity_upper_rejected(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  capacity ~ uniform 0Mbps 0Mbps
}
"""
        )
        res = check(parse(src, "zero-cap.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_zero_capacity_error("LeoFastHO"), res.errors)

    def test_zero_handover_interval_rejected(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 0s jitter 0s
  capacity ~ uniform 20Mbps 120Mbps
}
"""
        )
        res = check(parse(src, "zero-ho.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_zero_handover_error("LeoFastHO"), res.errors)

    def test_jitter_exceeds_interval_rejected(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 4s jitter 12s
  capacity ~ uniform 20Mbps 120Mbps
}
"""
        )
        res = check(parse(src, "jitter.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_jitter_exceeds_error("LeoFastHO"), res.errors)

    def test_zero_mobility_window_rejected(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  mobility_loss ~ burst p=0.08 window=0ms
}
"""
        )
        res = check(parse(src, "zero-mob.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_zero_mobility_window_error("LeoFastHO"), res.errors)

    def test_equal_positive_capacity_ok(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 80Mbps 80Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
"""
        )
        res = check(parse(src, "fixed-cap.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertIn("80-80Mbps", res.path_bound)

    def test_house_stamp_includes_capacity(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
"""
        )
        res = check(parse(src, "house-cap.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertIn("20-120Mbps", res.path_bound)
        self.assertIn("house", res.path_bound)


if __name__ == "__main__":
    unittest.main()
