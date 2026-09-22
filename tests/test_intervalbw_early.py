"""IntervalBw early-epoch Information law is a checkable refuse."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    check,
    intervalbw_early_tight_error,
)
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import HOUSE_EARLY_EPOCH_RTTS, HOUSE_EARLY_UNCERT_FLOOR

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


def _reach_shaped(reconfig_extra: str = "", *, posture: str = "observe") -> str:
    return f"""\
{OBSERVE_HDR}
controller Early {{
  posture {posture}
  compose Detect + SoftReprobe + Calendar + IntervalBw
        + WriteBudget + DualGateGuard

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
{reconfig_extra}    }}
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
    def test_early_floor_is_width_ratio(self):
        self.assertAlmostEqual(HOUSE_EARLY_UNCERT_FLOOR, 0.35)
        self.assertEqual(HOUSE_EARLY_EPOCH_RTTS, 2)


class TestCheckerStamp(unittest.TestCase):
    def test_reach_stamps_intervalbw_early(self):
        src = (ROOT / "examples" / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.intervalbw_early_uncertain)

    def test_ascent_stamps_intervalbw_early(self):
        src = (ROOT / "examples" / "ascent.vela").read_text(encoding="utf-8")
        res = check(parse(src, "ascent.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.intervalbw_early_uncertain)

    def test_cli_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(ROOT / "examples" / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("intervalbw-early-uncertain", out)
        self.assertIn("width-ratio>=0.35", out)
        self.assertIn("first 2 RTT", out)


class TestObserveRefuse(unittest.TestCase):
    def test_illegal_tight_uncertainty_after_enter(self):
        # Tiny illegal: force uncertainty below floor in Reconfig after enter.
        src = _reach_shaped("      uncertainty = 0.10\n")
        res = check(parse(src, "illegal-tight.vela"))
        self.assertFalse(res.ok)
        self.assertIn(
            intervalbw_early_tight_error(
                "Early",
                "uncertainty=0.1 (width-ratio below 0.35)",
            ),
            res.errors,
        )
        joined = "\n".join(res.errors)
        self.assertIn("stale min-RTT", joined)
        self.assertIn("first 2 RTT", joined)

    def test_illegal_prior_bw_carriage(self):
        src = _reach_shaped("      bw = prior.bw\n")
        res = check(parse(src, "illegal-prior.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("bw = prior.bw" in e for e in res.errors),
            res.errors,
        )

    def test_legal_no_force_ok(self):
        # Tiny legal: IntervalBw compose, typed Reconfig, no early force.
        src = _reach_shaped("")
        res = check(parse(src, "legal-early.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.intervalbw_early_uncertain)

    def test_uncertainty_at_floor_ok_in_reconfig(self):
        # Exactly at floor: not below, so not refused by this law.
        src = _reach_shaped("      uncertainty = 0.35\n")
        res = check(parse(src, "at-floor.vela"))
        self.assertTrue(res.ok, res.errors)


class TestReviewWarn(unittest.TestCase):
    def test_review_tight_uncertainty_warns(self):
        src = _reach_shaped("      uncertainty = 0.10\n", posture="review")
        res = check(parse(src, "review-tight.vela"))
        self.assertTrue(
            any("early uncertainty floor" in w for w in res.warnings),
            res.warnings,
        )
        self.assertFalse(
            any("IntervalBw refuses uncertainty" in e for e in res.errors),
            res.errors,
        )


class TestDocs(unittest.TestCase):
    def test_language_names_checkable_law(self):
        text = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("HOUSE_EARLY_UNCERT_FLOOR", text)
        self.assertIn("intervalbw-early-uncertain", text)
        self.assertIn("width-ratio", text)

    def test_ingress_names_stamp(self):
        text = (ROOT / "docs" / "INGRESS.md").read_text(encoding="utf-8")
        self.assertIn("intervalbw-early-uncertain", text)


if __name__ == "__main__":
    unittest.main()
