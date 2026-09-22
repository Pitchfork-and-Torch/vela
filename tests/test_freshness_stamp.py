"""Freshness / nested-prior law is a visible vela check stamp."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import FRESHNESS_CHECK_LINE, check
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


class TestFreshnessStamp(unittest.TestCase):
    def test_stamp_constant_names_freshness_and_prior(self):
        self.assertIn("freshness", FRESHNESS_CHECK_LINE)
        self.assertIn("invalidate sticks into nested", FRESHNESS_CHECK_LINE)
        self.assertIn("prior.x", FRESHNESS_CHECK_LINE)
        self.assertIn("enter Reprobe", FRESHNESS_CHECK_LINE)

    def test_reach_is_fresh(self):
        res = check(
            parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.freshness)

    def test_equinox_is_fresh(self):
        res = check(
            parse(
                (EX / "equinox.vela").read_text(encoding="utf-8"), "equinox.vela"
            )
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.freshness)

    def test_reach_check_prints_freshness_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(FRESHNESS_CHECK_LINE, out)
        self.assertIn("freshness", out)
        self.assertIn("prior.x", out)

    def test_equinox_check_prints_freshness_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(FRESHNESS_CHECK_LINE, out)

    def test_ascent_check_prints_freshness_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "ascent.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(FRESHNESS_CHECK_LINE, out)

    def test_nested_when_cannot_read_invalidated_bw(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      when bw.n >= 2 {
        freeze min_rtt for 1.4 * rtt
      }
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "nest-bw.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.freshness)
        self.assertTrue(
            any("invalidated" in e and "bw" in e for e in res.errors),
            res.errors,
        )

    def test_nested_when_cannot_freeze_invalidated_min_rtt(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      when p_ho > 0.5 {
        freeze min_rtt, bw for 1.4 * rtt
      }
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "nest-freeze.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.freshness)
        self.assertTrue(
            any("invalidated" in e and "min_rtt" in e for e in res.errors),
            res.errors,
        )

    def test_enter_after_invalidate_may_read_rtt(self):
        # SoftReprobe explore/fill uses current rtt; invalidate targets min_rtt/bw.
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "enter-ok.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.freshness)

    def test_after_enter_reprobe_prior_x_is_legal_remnant(self):
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
        res = check(parse(src, "prior-ok.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.freshness)
        self.assertTrue(res.affine)

    def test_after_enter_reprobe_current_name_refused(self):
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
        res = check(parse(src, "current-dead.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.affine)
        self.assertTrue(
            any("prior.rtt" in e or "e+1" in e or "Reprobe" in e for e in res.errors),
            res.errors,
        )

    def test_docs_cite_freshness_stamp(self):
        lang = (DOCS / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (DOCS / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("stamps `freshness`", lang)
        self.assertIn("Nested when/if/require inherit", lang)
        self.assertIn("prior.x", lang)
        self.assertIn("stamps `freshness`", equinox)
        self.assertIn("nested prior", equinox.lower())


if __name__ == "__main__":
    unittest.main()
