"""PredictiveFreeze wrong-calendar ease cap is a checkable law."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    check,
    freeze_ease_error,
    freeze_ease_warning,
)
from vela.cli import main as vela_main
from vela.kernel import (
    capped_pre_ho_pace,
    freeze_ease_of_remaining,
    freeze_ease_ok,
)
from vela.parser import parse
from vela.types import HOUSE_FREEZE_EASE_CAP, HOUSE_PRE_HO_PACE

ROOT = Path(__file__).resolve().parents[1]

OBSERVE_HDR = """\
lang vela 0.1
use std.epoch
use std.loss
use std.measure
use std.control
use std.path
use std.eval
"""


def _reach_shaped(body_extra: str = "", *, posture: str = "observe") -> str:
    return f"""\
{OBSERVE_HDR}
controller Cap {{
  posture {posture}
  compose Detect + SoftReprobe + Calendar + IntervalBw
        + WriteBudget + DualGateGuard + PredictiveFreeze

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

  when p_ho > 0.55 {{
    freeze min_rtt, bw for 1.4 * rtt
{body_extra}  }}
}}

path LeoFastHO {{
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}}

contract DualGate vs BBRv3approx {{
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  assert mean(goodput) >= baseline.goodput
  assert mean(p95) <= baseline.p95
  assert terrestrial.goodput >= 77 Mbps
  report ci(0.95), ablation
}}
"""


class TestHouseConstants(unittest.TestCase):
    def test_house_cap_is_six_percent(self):
        self.assertAlmostEqual(HOUSE_FREEZE_EASE_CAP, 0.06)
        self.assertAlmostEqual(HOUSE_PRE_HO_PACE, 0.94)
        self.assertAlmostEqual(HOUSE_PRE_HO_PACE + HOUSE_FREEZE_EASE_CAP, 1.0)


class TestKernelCap(unittest.TestCase):
    def test_default_remaining_is_house(self):
        self.assertAlmostEqual(capped_pre_ho_pace(), HOUSE_PRE_HO_PACE)

    def test_over_ease_clamps_to_house(self):
        # 20% ease (remaining 0.80) must not stall on a wrong calendar.
        self.assertAlmostEqual(capped_pre_ho_pace(0.80), HOUSE_PRE_HO_PACE)
        self.assertFalse(freeze_ease_ok(freeze_ease_of_remaining(0.80)))

    def test_at_cap_accepted(self):
        self.assertAlmostEqual(capped_pre_ho_pace(0.94), HOUSE_PRE_HO_PACE)
        self.assertTrue(freeze_ease_ok(0.06))

    def test_milder_ease_kept(self):
        self.assertAlmostEqual(capped_pre_ho_pace(0.97), 0.97)
        self.assertTrue(freeze_ease_ok(0.03))


class TestCheckerStamp(unittest.TestCase):
    def test_horizon_stamps_freeze_ease(self):
        src = (ROOT / "examples" / "horizon.vela").read_text(encoding="utf-8")
        res = check(parse(src, "horizon.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertAlmostEqual(res.freeze_ease_cap, HOUSE_FREEZE_EASE_CAP)

    def test_reach_stamps_freeze_ease(self):
        src = (ROOT / "examples" / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertAlmostEqual(res.freeze_ease_cap, HOUSE_FREEZE_EASE_CAP)

    def test_cli_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(ROOT / "examples" / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("freeze-ease<=6%", out)
        self.assertIn("wrong calendar cannot stall", out)


class TestObserveRefuse(unittest.TestCase):
    def test_observe_pace_scale_above_cap_refused(self):
        # 20% ease under observe: freeze-ease house law.
        src = _reach_shaped("    pace *= 0.80\n")
        res = check(parse(src, "over-ease.vela"))
        self.assertFalse(res.ok)
        joined = "\n".join(res.errors)
        self.assertIn(freeze_ease_error("Cap", 0.20), res.errors)
        self.assertIn("house cap 6%", joined)
        self.assertIn("wrong calendar cannot stall", joined)

    def test_observe_pace_scale_at_cap_is_passthrough_not_freeze(self):
        # Exactly 6% ease: freeze law ok; passthrough still refuses cruise write.
        src = _reach_shaped("    pace *= 0.94\n")
        res = check(parse(src, "at-cap.vela"))
        self.assertFalse(res.ok)
        joined = "\n".join(res.errors)
        self.assertNotIn("freeze ease", joined)
        self.assertIn("passthrough", joined)

    def test_observe_freeze_samples_ok(self):
        src = _reach_shaped("")
        res = check(parse(src, "freeze-ok.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertAlmostEqual(res.freeze_ease_cap, HOUSE_FREEZE_EASE_CAP)


class TestReviewWarn(unittest.TestCase):
    def test_review_pace_scale_above_cap_warns(self):
        src = _reach_shaped(
            "    pace *= 0.80\n",
            posture="review",
        )
        res = check(parse(src, "review-over.vela"))
        # review may keep a cruise write; freeze ease warns.
        self.assertIn(freeze_ease_warning("Cap", 0.20), res.warnings)
        self.assertTrue(any("freeze ease" in w for w in res.warnings))


class TestDocs(unittest.TestCase):
    def test_language_names_checkable_cap(self):
        text = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("HOUSE_FREEZE_EASE_CAP", text)
        self.assertIn("freeze-ease<=6%", text)
        self.assertIn("capped_pre_ho_pace", text)
        self.assertIn("Freeze ease cap", text)


if __name__ == "__main__":
    unittest.main()
