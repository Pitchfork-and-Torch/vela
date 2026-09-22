"""FairMode AIMD@1.0xBDP is a checkable compose/mech cite (LANGUAGE Fairness)."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    check,
    fair_mode_chase_warning,
    fair_mode_without_holdout_warning,
    program_stamps_fair_mode,
)
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import FAIR_MODE_STAMP, FAIRNESS_SCENARIO, HOUSE_FAIR_MODE_BDP_FRAC

ROOT = Path(__file__).resolve().parents[1]

OBSERVE_HDR = """\
lang vela 0.4

use std.epoch
use std.loss
use std.measure
use std.control
use std.path
use std.eval
use std.mech
"""


def _controller(*, compose: str, posture: str = "observe", contract: str = "") -> str:
    return f"""\
{OBSERVE_HDR}
controller Cap {{
  posture {posture}
  compose {compose}

  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
    delay_ratio: Ratio
    p_ho: Prob

  on Reconfig(e) match e {{
    RttHop => {{
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }}
    Flicker => {{
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }}
  }}

  on Loss(k) match k {{
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => require delay_ratio > 1.35 then cut(0.72) else hold
  }}
}}

path LeoFastHO {{
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}}

{contract}
"""


HOLD_OUT = """\
contract DualGate vs BBRv3approx {
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  scenario leo_multi
  assert mean(goodput) >= baseline.goodput
  assert mean(p95) <= baseline.p95
  assert terrestrial.goodput >= 77 Mbps
  assert mean(jain) >= 0.85
  report ci(0.95), ablation
}
"""

REACH_COMPOSE = (
    "Detect + SoftReprobe + Calendar + IntervalBw "
    "+ WriteBudget + DualGateGuard"
)


class TestHouseConstants(unittest.TestCase):
    def test_aimd_around_one_bdp(self):
        self.assertAlmostEqual(HOUSE_FAIR_MODE_BDP_FRAC, 1.0)
        self.assertEqual(FAIR_MODE_STAMP, "AIMD@1.0xBDP")
        self.assertEqual(FAIRNESS_SCENARIO, "leo_multi")


class TestCheckerStamp(unittest.TestCase):
    def test_fair_example_stamps_fair_mode(self):
        src = (ROOT / "examples" / "fair.vela").read_text(encoding="utf-8")
        prog = parse(src, "fair.vela")
        self.assertTrue(program_stamps_fair_mode(prog))
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.fair_mode, FAIR_MODE_STAMP)
        self.assertEqual(res.fairness, FAIRNESS_SCENARIO)
        self.assertTrue(res.observe_only)
        self.assertEqual(res.closed_writes, [])

    def test_reach_does_not_stamp_fair_mode(self):
        src = (ROOT / "examples" / "reach.vela").read_text(encoding="utf-8")
        prog = parse(src, "reach.vela")
        self.assertFalse(program_stamps_fair_mode(prog))
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.fair_mode, "")
        self.assertEqual(res.fairness, "")

    def test_fairmode_compose_stamps_without_cruise(self):
        src = _controller(
            compose=REACH_COMPOSE + " + FairMode",
            contract=HOLD_OUT,
        )
        res = check(parse(src, "cap.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.fair_mode, FAIR_MODE_STAMP)
        self.assertTrue(res.observe_only)
        self.assertEqual(res.closed_writes, [])

    def test_cli_prints_stamp_on_fair(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(ROOT / "examples" / "fair.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("fair_mode=AIMD@1.0xBDP", out)
        self.assertIn("not closed-write cruise", out)
        self.assertIn("observe-only", out)


class TestFairModeWarnings(unittest.TestCase):
    def test_fairmode_without_holdout_warns(self):
        src = _controller(compose=REACH_COMPOSE + " + FairMode")
        res = check(parse(src, "cap.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.fair_mode, FAIR_MODE_STAMP)
        self.assertIn(fair_mode_without_holdout_warning("Cap"), res.warnings)

    def test_fairmode_with_horizonchase_warns_not_enable(self):
        src = _controller(
            compose=REACH_COMPOSE + " + FairMode + HorizonChase",
            posture="review",
            contract=HOLD_OUT,
        )
        res = check(parse(src, "cap.vela"))
        self.assertIn(fair_mode_chase_warning("Cap"), res.warnings)
        # review + HorizonChase is closed-write; stamp still cites FairMode.
        self.assertEqual(res.fair_mode, FAIR_MODE_STAMP)
        self.assertFalse(res.observe_only)


class TestDocs(unittest.TestCase):
    def test_language_names_checkable_cite(self):
        text = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("HOUSE_FAIR_MODE_BDP_FRAC", text)
        self.assertIn("fair_mode=AIMD@1.0xBDP", text)
        self.assertIn("`FairMode`", text)
        self.assertIn("does not enable closed-write cruise", text)

    def test_ingress_names_stamp(self):
        text = (ROOT / "docs" / "INGRESS.md").read_text(encoding="utf-8")
        self.assertIn("fair_mode=AIMD@1.0xBDP", text)


if __name__ == "__main__":
    unittest.main()
