"""Path realism: reject dead LeoPath rails (capacity/handover/mobility/inverted).

House LeoFastHO stays 12s+/-4s when valid. No next_capacity / future PathState.
Distinct from contract-duration non-positive checks.
"""
from __future__ import annotations

import unittest

from vela.checker import check
from vela.parser import parse
from vela.path import (
    HOUSE_HANDOVER_INTERVAL_S,
    HOUSE_HANDOVER_JITTER_S,
    parse_path_model,
)
from vela.ast import PathModel


def _prog(**overrides: str) -> str:
    rails = {
        "handover": "every 12s jitter 4s",
        "rtt_jump": "uniform 20ms 90ms",
        "capacity": "uniform 20Mbps 120Mbps",
        "mobility_loss": "burst p=0.08 window=400ms",
    }
    rails.update(overrides)
    body = "\n".join(f"  {k} ~ {v}" for k, v in rails.items())
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
{body}
}}
contract DualGate vs BBR {{
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  assert mean(goodput) >= 1
  assert terrestrial.goodput >= 77 Mbps
}}
"""


class TestPathRealismRails(unittest.TestCase):
    def test_house_rails_ok(self):
        res = check(parse(_prog(), "house.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertIn("LeoFastHO:leo_fast_ho", res.path_bound)
        self.assertIn(f"{HOUSE_HANDOVER_INTERVAL_S:g}s", res.path_bound)
        self.assertIn(f"+/-{HOUSE_HANDOVER_JITTER_S:g}s", res.path_bound)

    def test_zero_capacity_rejected(self):
        res = check(parse(_prog(capacity="uniform 0Mbps 0Mbps"), "zero-cap.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("capacity" in e and "positive" in e for e in res.errors),
            res.errors,
        )

    def test_zero_capacity_upper_rejected(self):
        res = check(parse(_prog(capacity="uniform 10Mbps 0Mbps"), "zero-hi.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("capacity" in e and "positive" in e for e in res.errors),
            res.errors,
        )

    def test_equal_positive_capacity_ok(self):
        res = check(parse(_prog(capacity="uniform 50Mbps 50Mbps"), "eq-cap.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_inverted_capacity_rejected(self):
        res = check(
            parse(_prog(capacity="uniform 120Mbps 20Mbps"), "inv-cap.vela")
        )
        self.assertFalse(res.ok)
        self.assertTrue(
            any("capacity" in e and "inverted" in e for e in res.errors),
            res.errors,
        )

    def test_inverted_rtt_jump_rejected(self):
        res = check(
            parse(_prog(rtt_jump="uniform 90ms 20ms"), "inv-rtt.vela")
        )
        self.assertFalse(res.ok)
        self.assertTrue(
            any("rtt_jump" in e and "inverted" in e for e in res.errors),
            res.errors,
        )

    def test_equal_rtt_bounds_ok(self):
        res = check(parse(_prog(rtt_jump="uniform 40ms 40ms"), "eq-rtt.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_zero_handover_period_rejected(self):
        res = check(
            parse(_prog(handover="every 0s jitter 4s"), "zero-ho.vela")
        )
        self.assertFalse(res.ok)
        self.assertTrue(
            any("handover" in e and "positive" in e for e in res.errors),
            res.errors,
        )
        # Dead period must not stamp as bound house rail.
        self.assertTrue(
            res.path_bound is None
            or "unbound" in (res.path_bound or "")
            or "0s" not in (res.path_bound or ""),
            res.path_bound,
        )

    def test_zero_mobility_window_rejected(self):
        res = check(
            parse(
                _prog(mobility_loss="burst p=0.08 window=0ms"),
                "zero-mob.vela",
            )
        )
        self.assertFalse(res.ok)
        self.assertTrue(
            any("mobility_loss" in e and "positive" in e for e in res.errors),
            res.errors,
        )

    def test_parse_path_model_clears_dead_handover(self):
        law = parse_path_model(
            PathModel(
                name="LeoFastHO",
                fields={
                    "handover": "every 0s jitter 4s",
                    "rtt_jump": "uniform 20ms 90ms",
                    "capacity": "uniform 20Mbps 120Mbps",
                    "mobility_loss": "burst p=0.08 window=400ms",
                },
            )
        )
        self.assertTrue(any("handover" in e for e in law.errors))
        self.assertIsNone(law.handover_interval_s)
        self.assertFalse(law.bound)


if __name__ == "__main__":
    unittest.main()
