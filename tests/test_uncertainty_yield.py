"""Uncertainty-scaled yield (p95) is a checkable language/kernel law."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    check,
    uncertainty_yield_error,
    uncertainty_yield_warning,
)
from vela.cli import main as vela_main
from vela.kernel import u_yield_should_cut, u_yield_should_reclaim
from vela.parser import parse
from vela.types import (
    HOUSE_U_RECLAIM_BDP_FRAC,
    HOUSE_U_RECLAIM_DELAY_RATIO,
    HOUSE_U_RECLAIM_P_HO,
    HOUSE_U_RECLAIM_UNCERT,
    HOUSE_U_YIELD_DELAY_RATIO,
    HOUSE_U_YIELD_UNCERT,
)

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

{body_extra}}}

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
    def test_house_yield_gates(self):
        self.assertAlmostEqual(HOUSE_U_YIELD_UNCERT, 0.50)
        self.assertAlmostEqual(HOUSE_U_YIELD_DELAY_RATIO, 1.62)
        self.assertAlmostEqual(HOUSE_U_RECLAIM_UNCERT, 0.25)
        self.assertAlmostEqual(HOUSE_U_RECLAIM_DELAY_RATIO, 1.26)
        self.assertAlmostEqual(HOUSE_U_RECLAIM_P_HO, 0.20)
        self.assertAlmostEqual(HOUSE_U_RECLAIM_BDP_FRAC, 1.16)


class TestKernelGates(unittest.TestCase):
    def test_cut_needs_high_u_and_delay(self):
        self.assertTrue(u_yield_should_cut(0.51, 1.63))
        self.assertFalse(u_yield_should_cut(0.49, 1.63))
        self.assertFalse(u_yield_should_cut(0.51, 1.61))

    def test_reclaim_needs_tight_epoch(self):
        self.assertTrue(
            u_yield_should_reclaim(0.20, 1.20, 0.10, 1000.0, 1000.0)
        )
        self.assertFalse(
            u_yield_should_reclaim(0.30, 1.20, 0.10, 1000.0, 1000.0)
        )
        self.assertFalse(
            u_yield_should_reclaim(0.20, 1.20, 0.10, 1200.0, 1000.0)
        )


class TestCheckerStamp(unittest.TestCase):
    def test_reach_stamps_u_yield(self):
        src = (ROOT / "examples" / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.uncertainty_scaled_yield)

    def test_horizon_stamps_u_yield(self):
        src = (ROOT / "examples" / "horizon.vela").read_text(encoding="utf-8")
        res = check(parse(src, "horizon.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.uncertainty_scaled_yield)

    def test_ascent_stamps_u_yield(self):
        src = (ROOT / "examples" / "ascent.vela").read_text(encoding="utf-8")
        res = check(parse(src, "ascent.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.uncertainty_scaled_yield)

    def test_cli_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(ROOT / "examples" / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("uncertainty-scaled-yield", out)
        self.assertIn("gated on u|p_ho", out)
        self.assertIn("house u>=0.5", out)


class TestObserveRefuse(unittest.TestCase):
    def test_delay_only_yield_refused(self):
        # v3.4-p95 class: yield on delay alone, no uncertainty|p_ho gate.
        src = _reach_shaped(
            "  when delay_ratio > 1.62 {\n    cwnd *= 0.98\n  }\n"
        )
        res = check(parse(src, "delay-only.vela"))
        self.assertFalse(res.ok)
        self.assertIn(uncertainty_yield_error("Cap"), res.errors)
        joined = "\n".join(res.errors)
        self.assertIn("uncertainty|p_ho", joined)
        self.assertIn("every-ACK", joined)

    def test_every_ack_yield_refused(self):
        src = _reach_shaped("  every ack {\n    cwnd *= 0.98\n  }\n")
        res = check(parse(src, "every-ack.vela"))
        self.assertFalse(res.ok)
        self.assertIn(uncertainty_yield_error("Cap"), res.errors)

    def test_uncertainty_gate_skips_u_yield_error(self):
        # Gated yield still fails passthrough under observe; u-yield law ok.
        src = _reach_shaped(
            "  when uncertainty > 0.50 {\n    cwnd *= 0.98\n  }\n"
        )
        res = check(parse(src, "u-gated.vela"))
        self.assertFalse(res.ok)
        joined = "\n".join(res.errors)
        self.assertNotIn("uncertainty-scaled yield", joined)
        self.assertIn("passthrough", joined)

    def test_p_ho_gate_skips_u_yield_error(self):
        src = _reach_shaped("  when p_ho > 0.20 {\n    cwnd *= 0.98\n  }\n")
        res = check(parse(src, "pho-gated.vela"))
        self.assertFalse(res.ok)
        joined = "\n".join(res.errors)
        self.assertNotIn("uncertainty-scaled yield", joined)
        self.assertIn("passthrough", joined)

    def test_flagship_ok(self):
        src = _reach_shaped("")
        res = check(parse(src, "ok.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.uncertainty_scaled_yield)


class TestReviewWarn(unittest.TestCase):
    def test_review_ungated_yield_warns(self):
        src = _reach_shaped(
            "  when delay_ratio > 1.62 {\n    cwnd *= 0.98\n  }\n",
            posture="review",
        )
        res = check(parse(src, "review-ungated.vela"))
        self.assertIn(uncertainty_yield_warning("Cap"), res.warnings)
        self.assertTrue(
            any("uncertainty-scaled yield" in w for w in res.warnings)
        )


class TestDocs(unittest.TestCase):
    def test_language_names_checkable_yield(self):
        text = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("HOUSE_U_YIELD_UNCERT", text)
        self.assertIn("uncertainty-scaled-yield", text)
        self.assertIn("u_yield_should_cut", text)
        self.assertIn("HOUSE_U_RECLAIM_BDP_FRAC", text)


if __name__ == "__main__":
    unittest.main()
