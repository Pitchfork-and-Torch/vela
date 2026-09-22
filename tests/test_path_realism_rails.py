"""path-realism-rails: dead LeoPath rails + flicker + calendar p_ho.

Backlog path-realism-rails: reject non-positive capacity upper, zero
handover period, zero mobility_loss window, inverted rtt/capacity.
House LeoFastHO stays 12s+/-4s. No next_capacity / future PathState.
Extensions beyond flicker law: handover/flicker jitter bounds, capacity
Mbps honesty on the stamp, calendar p_ho = past gaps.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check
from vela.oracle import ORACLE_NAMES, refuse_oracle_hint
from vela.parser import parse
from vela.path import (
    HOUSE_HANDOVER_INTERVAL_S,
    HOUSE_HANDOVER_JITTER_S,
    HOUSE_SOFT_REPROBE_CUT,
    STARLINK_V2_FLICKER_INTERVAL_S,
    STARLINK_V2_FLICKER_JITTER_S,
    path_cadence_error,
    path_inverted_range_error,
    path_jitter_exceeds_error,
    path_oracle_field_error,
    path_reconfig_alias_error,
    path_zero_capacity_error,
    path_zero_handover_error,
    path_zero_mobility_window_error,
)


ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def _prog(**fields: str) -> str:
    body = {
        "handover": "every 12s jitter 4s",
        "rtt_jump": "uniform 20ms 90ms",
        "capacity": "uniform 20Mbps 120Mbps",
        "mobility_loss": "burst p=0.08 window=400ms",
    }
    body.update(fields)
    # Drop keys set to None to omit the field.
    path_lines = "\n".join(
        f"  {k} ~ {v}" for k, v in body.items() if v is not None
    )
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

    def test_zero_capacity_upper_rejected(self):
        res = check(parse(_prog(capacity="uniform 0Mbps 0Mbps"), "zero-cap.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_zero_capacity_error("LeoFastHO"), res.errors)

    def test_zero_handover_interval_rejected(self):
        res = check(parse(_prog(handover="every 0s jitter 0s"), "zero-ho.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_zero_handover_error("LeoFastHO"), res.errors)

    def test_handover_jitter_exceeds_interval_rejected(self):
        res = check(parse(_prog(handover="every 4s jitter 12s"), "jitter-ho.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_jitter_exceeds_error("LeoFastHO", "handover"), res.errors)

    def test_zero_mobility_window_rejected(self):
        res = check(
            parse(_prog(mobility_loss="burst p=0.08 window=0ms"), "zero-mob.vela")
        )
        self.assertFalse(res.ok)
        self.assertIn(path_zero_mobility_window_error("LeoFastHO"), res.errors)

    def test_equal_positive_bounds_ok(self):
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
        self.assertIn("50-50Mbps", res.path_bound)

    def test_house_rails_stamp_capacity_and_calendar(self):
        res = check(parse(_prog(), "house.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertIn("LeoFastHO:leo_fast_ho", res.path_bound)
        self.assertIn("12s+/-4s", res.path_bound)
        self.assertIn("20-120Mbps", res.path_bound)
        self.assertIn("house", res.path_bound)
        self.assertIn("calendar=past-gaps", res.path_bound)
        self.assertTrue(
            any("calendar p_ho from past inter-hop gaps" in w for w in res.warnings),
            res.warnings,
        )
        self.assertEqual(HOUSE_HANDOVER_INTERVAL_S, 12.0)
        self.assertEqual(HOUSE_HANDOVER_JITTER_S, 4.0)
        self.assertEqual(HOUSE_SOFT_REPROBE_CUT, 0.58)

    def test_flicker_starlink_v2_ok_not_hop(self):
        res = check(
            parse(
                _prog(
                    flicker=(
                        f"every {STARLINK_V2_FLICKER_INTERVAL_S:g}s "
                        f"jitter {STARLINK_V2_FLICKER_JITTER_S:g}s"
                    )
                ),
                "flicker.vela",
            )
        )
        self.assertTrue(res.ok, res.errors)
        self.assertIn("flicker=", res.path_bound)
        self.assertIn("not hop", res.path_bound)
        self.assertTrue(any("not a hop" in w for w in res.warnings), res.warnings)
        self.assertTrue(any("0.58" in w for w in res.warnings), res.warnings)

    def test_zero_flicker_interval_rejected(self):
        res = check(
            parse(_prog(flicker="every 0s jitter 1.2s"), "zero-flicker.vela")
        )
        self.assertFalse(res.ok)
        self.assertIn(path_cadence_error("LeoFastHO", "flicker"), res.errors)

    def test_flicker_jitter_exceeds_rejected(self):
        res = check(parse(_prog(flicker="every 1s jitter 2s"), "flicker-j.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_cadence_error("LeoFastHO", "flicker"), res.errors)

    def test_hop_alias_rejected(self):
        src = _prog()
        src = src.replace(
            "mobility_loss ~ burst p=0.08 window=400ms",
            "hop ~ every 12s jitter 4s",
        )
        res = check(parse(src, "hop-alias.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_reconfig_alias_error("LeoFastHO", "hop", "RttHop"), res.errors)

    def test_next_capacity_path_field_rejected(self):
        src = _prog()
        src = src.replace(
            "mobility_loss ~ burst p=0.08 window=400ms",
            "next_capacity ~ uniform 20Mbps 120Mbps",
        )
        res = check(parse(src, "oracle-field.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_oracle_field_error("LeoFastHO", "next_capacity"), res.errors)

    def test_oracle_kernel_still_strips_next_capacity(self):
        self.assertIn("next_capacity", ORACLE_NAMES)
        clean = refuse_oracle_hint(
            {"capacity_bps": 1e8, "next_capacity_bps": 9e9, "rtt_s": 0.04}
        )
        self.assertEqual(clean, {"capacity_bps": 1e8, "rtt_s": 0.04})

    def test_starlink_flicker_example_checks(self):
        src = (EX / "starlink_flicker.vela").read_text(encoding="utf-8")
        res = check(parse(src, "starlink_flicker.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.observe_only)
        self.assertIn("flicker=", res.path_bound)
        self.assertIn("calendar=past-gaps", res.path_bound)
        self.assertIn("20-120Mbps", res.path_bound)

    def test_flagship_reach_ascent_still_house(self):
        for name in ("reach.vela", "ascent.vela"):
            src = (EX / name).read_text(encoding="utf-8")
            res = check(parse(src, name))
            self.assertTrue(res.ok, (name, res.errors))
            self.assertIn("house", res.path_bound)
            self.assertIn("calendar=past-gaps", res.path_bound)
            self.assertIn("20-120Mbps", res.path_bound)


if __name__ == "__main__":
    unittest.main()
