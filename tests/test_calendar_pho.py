"""Calendar p_ho honesty: past-gaps stamp, not next-sat oracle."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check, controller_stamps_calendar_p_ho
from vela.cli import main as vela_main
from vela.oracle import calendar_oracle_error, oracle_error
from vela.parser import parse
from vela.types import CALENDAR_P_HO_STAMP

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


def _calendar_src(body_extra: str = "", *, with_calendar: bool = True) -> str:
    mechs = "Detect + SoftReprobe + IntervalBw"
    if with_calendar:
        mechs = "Detect + SoftReprobe + Calendar + IntervalBw"
    return f"""\
{OBSERVE_HDR}
controller Cal {{
  posture observe
  compose {mechs}
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
{body_extra}    }}
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


class TestStampConstant(unittest.TestCase):
    def test_stamp_is_past_gaps(self):
        self.assertEqual(CALENDAR_P_HO_STAMP, "past-gaps")


class TestCheckerStamp(unittest.TestCase):
    def test_reach_stamps_calendar_p_ho(self):
        src = (ROOT / "examples" / "reach.vela").read_text(encoding="utf-8")
        prog = parse(src, "reach.vela")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.calendar_p_ho, CALENDAR_P_HO_STAMP)
        self.assertTrue(controller_stamps_calendar_p_ho(prog.controllers[0]))

    def test_horizon_without_calendar_does_not_stamp(self):
        src = (ROOT / "examples" / "horizon.vela").read_text(encoding="utf-8")
        prog = parse(src, "horizon.vela")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.calendar_p_ho, "")
        self.assertFalse(controller_stamps_calendar_p_ho(prog.controllers[0]))

    def test_cli_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(ROOT / "examples" / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("calendar-p_ho=past-gaps", out)
        self.assertIn("not next-sat oracle", out)
        self.assertIn("no-oracle", out)


class TestCalendarOracleRefuse(unittest.TestCase):
    def test_next_capacity_on_calendar_path_refused(self):
        src = _calendar_src("      pace = next_capacity\n", with_calendar=True)
        res = check(parse(src, "cal-oracle.vela"))
        self.assertFalse(res.ok)
        self.assertIn(calendar_oracle_error("Cal", "next_capacity"), res.errors)
        joined = "\n".join(res.errors)
        self.assertIn("Calendar p_ho=past-gaps", joined)
        self.assertIn("not next-sat oracle", joined)
        self.assertFalse(res.no_oracle)
        # Still stamps Calendar honesty when composed, even if check fails.
        self.assertEqual(res.calendar_p_ho, CALENDAR_P_HO_STAMP)

    def test_next_capacity_without_calendar_uses_generic_no_oracle(self):
        src = _calendar_src("      pace = next_capacity\n", with_calendar=False)
        res = check(parse(src, "no-cal-oracle.vela"))
        self.assertFalse(res.ok)
        self.assertIn(oracle_error("Cal", "next_capacity"), res.errors)
        joined = "\n".join(res.errors)
        self.assertNotIn("Calendar p_ho=past-gaps", joined)
        self.assertEqual(res.calendar_p_ho, "")


class TestDocs(unittest.TestCase):
    def test_language_names_calendar_stamp(self):
        text = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("calendar-p_ho=past-gaps", text)
        self.assertIn("not a next-sat oracle", text)
        self.assertIn("Calendar p_ho", text)

    def test_ingress_names_calendar_stamp(self):
        text = (ROOT / "docs" / "INGRESS.md").read_text(encoding="utf-8")
        self.assertIn("calendar-p_ho=past-gaps", text)
        self.assertIn("next-sat oracle", text)
        self.assertIn("freeze-ease", text)


if __name__ == "__main__":
    unittest.main()
