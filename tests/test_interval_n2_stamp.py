"""Uncertainty law: Interval point-use n>=2 is a visible vela check stamp."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(body: str, compose: str = "Detect + IntervalBw") -> str:
    return f"""
lang vela 0.1
controller Probe {{
  posture observe
  compose {compose}
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
{body}
{LOSS}
}}
"""


class TestIntervalN2Stamp(unittest.TestCase):
    def test_intervalbw_compose_stamps(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
    Flicker => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
  }
"""
        )
        res = check(parse(src, "with-ibw.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.interval_n2)

    def test_interval_signal_without_ibw_stamps(self):
        # Interval signal alone still activates the uncertainty law surface.
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
    Flicker => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
  }
""",
            compose="Detect + SoftReprobe",
        )
        res = check(parse(src, "interval-signal.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.interval_n2)

    def test_no_interval_no_stamp(self):
        src = f"""
lang vela 0.1
controller Probe {{
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {{
    RttHop => {{
      invalidate min_rtt
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }}
    Flicker => {{
      invalidate min_rtt
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }}
  }}
{LOSS}
}}
"""
        res = check(parse(src, "no-interval.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.interval_n2)

    def test_reach_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("interval_n>=2", out)
        self.assertIn("uncertainty-n", out)
        self.assertIn("bw as point requires n>=2", out)
        # SoftReprobe house cut stays 0.58 (typed reconfig line).
        self.assertIn("0.58", out)

    def test_horizon_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "horizon.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("interval_n>=2", out)
        self.assertIn("uncertainty-n", out)

    def test_equinox_check_prints_stamp(self):
        eq = EX / "equinox.vela"
        if not eq.is_file():
            self.skipTest("equinox.vela missing")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(eq)])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("interval_n>=2", out)
        self.assertIn("uncertainty-n", out)

    def test_docs_name_visible_stamps(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("interval_n>=2", lang)
        self.assertIn("uncertainty-n", lang)
        self.assertIn("interval_n>=2", equinox)
        self.assertIn("uncertainty-n", equinox)
        self.assertIn("0.58", equinox)

    def test_law_still_errors_unguarded_point_use(self):
        # Stamp is visibility; existing type error remains load-bearing.
        src = _src(
            """
  when p_ho > 0.5 {
    pace = bw.mid
  }
"""
        )
        res = check(parse(src, "unguarded.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(res.interval_n2)
        self.assertTrue(
            any("used as a point requires" in e and "n >= 2" in e for e in res.errors),
            res.errors,
        )


if __name__ == "__main__":
    unittest.main()
