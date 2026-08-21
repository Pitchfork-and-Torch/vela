"""No-oracle law: future PathState is a type error and a kernel drop."""
from __future__ import annotations

import unittest

from vela.checker import check
from vela.ir import VelaConfig
from vela.kernel import HorizonCCA
from vela.oracle import ORACLE_NAMES, refuse_oracle_hint
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
    delay_ratio: Ratio
{body}
{LOSS}
}}
"""


class TestOracleRefuse(unittest.TestCase):
    def test_kernel_forwards_none_for_next_capacity(self):
        class FakeLeo:
            def __init__(self):
                self.kw = None

            def on_path_hint(self, t, reconfigured, **kw):
                self.kw = kw

        h = HorizonCCA.__new__(HorizonCCA)
        h.cfg = VelaConfig()
        h._leo = FakeLeo()
        h.on_path_hint(
            1.0,
            True,
            next_capacity_bps=1.2e8,
            next_handover_t=14.0,
            capacity_bps=6e7,
            rtt_s=0.05,
        )
        self.assertIsNone(h._leo.kw.get("next_capacity_bps"))
        self.assertNotIn("next_handover_t", h._leo.kw)
        self.assertEqual(h._leo.kw.get("capacity_bps"), 6e7)
        self.assertEqual(h._leo.kw.get("rtt_s"), 0.05)

    def test_hint_kwargs_drop_next_capacity(self):
        clean = refuse_oracle_hint(
            {
                "capacity_bps": 8e7,
                "next_capacity_bps": 1.2e8,
                "next_handover_t": 12.0,
                "rtt_s": 0.04,
                "epoch": 3,
            }
        )
        self.assertNotIn("next_capacity_bps", clean)
        self.assertNotIn("next_handover_t", clean)
        self.assertEqual(clean["capacity_bps"], 8e7)
        self.assertEqual(clean["rtt_s"], 0.04)
        self.assertEqual(clean["epoch"], 3)

    def test_oracle_names_are_closed(self):
        self.assertIn("next_capacity", ORACLE_NAMES)
        self.assertIn("next_capacity_bps", ORACLE_NAMES)


class TestOracleChecker(unittest.TestCase):
    def test_read_next_capacity_is_error(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58)
      pace = next_capacity
    }
    Flicker => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58)
    }
  }
"""
        )
        res = check(parse(src, "oracle.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("no-oracle" in e for e in res.errors))
        self.assertTrue(any("next_capacity" in e for e in res.errors))
        self.assertFalse(res.no_oracle)

    def test_path_next_capacity_attr_is_error(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => enter Reprobe(cut: 0.58)
    Flicker => enter Reprobe(cut: 0.58)
  }
  when next_capacity_bps > 0 {
    freeze bw
  }
"""
        )
        res = check(parse(src, "path-oracle.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("no-oracle" in e for e in res.errors))

    def test_reach_is_no_oracle(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "examples" / "reach.vela").read_text(
            encoding="utf-8"
        )
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.no_oracle)


if __name__ == "__main__":
    unittest.main()
