"""prior.x carry law is a visible vela check stamp (fail closed)."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import PRIOR_X_CARRY_CHECK_LINE, affine_epoch_error, check
from vela.cli import main as vela_main
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
DOCS = ROOT / "docs"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(body: str, *, posture: str = "observe") -> str:
    return f"""
lang vela 0.4
controller Probe {{
  posture {posture}
  compose Detect + SoftReprobe + IntervalBw
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
{body}
{LOSS}
}}
"""


class TestPriorXCarryStamp(unittest.TestCase):
    def test_stamp_constant_names_prior_x_carry(self):
        self.assertIn("prior_x_carry", PRIOR_X_CARRY_CHECK_LINE)
        self.assertIn("enter Reprobe", PRIOR_X_CARRY_CHECK_LINE)
        self.assertIn("prior.x", PRIOR_X_CARRY_CHECK_LINE)
        self.assertIn("fail closed", PRIOR_X_CARRY_CHECK_LINE)

    def test_reach_prior_x_carry(self):
        res = check(
            parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.prior_x_carry)

    def test_equinox_prior_x_carry(self):
        res = check(
            parse(
                (EX / "equinox.vela").read_text(encoding="utf-8"), "equinox.vela"
            )
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.prior_x_carry)

    def test_reach_check_prints_prior_x_carry_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(PRIOR_X_CARRY_CHECK_LINE, out)
        self.assertIn("prior_x_carry", out)
        self.assertIn("0.58", out)

    def test_equinox_check_prints_prior_x_carry_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(PRIOR_X_CARRY_CHECK_LINE, out)

    def test_ascent_check_prints_prior_x_carry_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "ascent.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(PRIOR_X_CARRY_CHECK_LINE, out)

    def test_after_enter_reprobe_prior_x_is_legal_carry(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      enter Reprobe(cut: 0.58)
      let x = prior.rtt
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "prior-carry-ok.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.prior_x_carry)
        self.assertTrue(res.affine)

    def test_after_enter_reprobe_current_sample_fail_closed(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      enter Reprobe(cut: 0.58)
      let x = rtt
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "prior-carry-fail.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.prior_x_carry)
        self.assertFalse(res.affine)
        self.assertIn(affine_epoch_error("Probe", "rtt"), res.errors)

    def test_enter_args_may_use_current_rtt_before_epoch_edge(self):
        # explore/fill bind scale in the enter args; epoch advances after.
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "enter-args-ok.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.prior_x_carry)

    def test_docs_cite_prior_x_carry_stamp(self):
        lang = (DOCS / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (DOCS / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("stamps `prior_x_carry`", lang)
        self.assertIn("prior.x carry", lang)
        self.assertIn("stamps `prior_x_carry`", equinox)
        self.assertIn("prior.x carry", equinox)


if __name__ == "__main__":
    unittest.main()
