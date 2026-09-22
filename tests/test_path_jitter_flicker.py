"""path: handover/flicker cadence bounds + flicker vs hop naming.

Distinct from capacity upper-bound (#26), inverted uniform ranges (#22),
and zero mobility window (#24). Flicker is mid-epoch capacity, not RttHop.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check
from vela.parser import parse
from vela.path import (
    STARLINK_V2_FLICKER_INTERVAL_S,
    STARLINK_V2_FLICKER_JITTER_S,
    path_cadence_error,
)


ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def _prog(path_body: str, uses: str = "use std.path") -> str:
    return f"""
lang vela 0.1
{uses}
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


class TestPathJitterFlicker(unittest.TestCase):
    def test_zero_handover_interval_rejected(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 0s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
"""
        )
        res = check(parse(src, "zero-ho.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_cadence_error("LeoFastHO", "handover"), res.errors)

    def test_jitter_exceeds_interval_rejected(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 2s jitter 5s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
"""
        )
        res = check(parse(src, "jitter-ho.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_cadence_error("LeoFastHO", "handover"), res.errors)

    def test_equal_jitter_and_interval_ok(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 4s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
"""
        )
        res = check(parse(src, "eq-ho.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_zero_flicker_interval_rejected(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  flicker ~ every 0s jitter 1.2s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
"""
        )
        res = check(parse(src, "zero-flicker.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_cadence_error("LeoFastHO", "flicker"), res.errors)

    def test_flicker_jitter_exceeds_interval_rejected(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  flicker ~ every 1s jitter 2s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
"""
        )
        res = check(parse(src, "flicker-jitter.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_cadence_error("LeoFastHO", "flicker"), res.errors)

    def test_starlink_v2_flicker_ok_and_warns_not_hop(self):
        src = _prog(
            f"""
path LeoFastHO {{
  handover ~ every 12s jitter 4s
  flicker ~ every {STARLINK_V2_FLICKER_INTERVAL_S:g}s jitter {STARLINK_V2_FLICKER_JITTER_S:g}s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}}
"""
        )
        res = check(parse(src, "v2-flicker.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("not a hop" in w for w in res.warnings), res.warnings)
        self.assertIn("flicker=", res.path_bound)

    def test_hop_field_alias_is_type_error(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  hop ~ every 12s jitter 4s
}
"""
        )
        res = check(parse(src, "hop-alias.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("RttHop is a Reconfig kind" in e for e in res.errors), res.errors)

    def test_Flicker_reconfig_name_as_path_field_errors(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  Flicker ~ every 2.8s jitter 1.2s
}
"""
        )
        res = check(parse(src, "Flicker-alias.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("Flicker is a Reconfig kind" in e for e in res.errors), res.errors)

    def test_starlink_flicker_example_checks(self):
        src = (EX / "starlink_flicker.vela").read_text(encoding="utf-8")
        res = check(parse(src, "starlink_flicker.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.observe_only)
        self.assertTrue(any("not a hop" in w for w in res.warnings), res.warnings)

    def test_ascent_erased_example_checks(self):
        src = (EX / "ascent_erased.vela").read_text(encoding="utf-8")
        res = check(parse(src, "ascent_erased.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hint_fail_closed)
        self.assertTrue(res.observe_only)


if __name__ == "__main__":
    unittest.main()
