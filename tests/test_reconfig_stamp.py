"""Typed reconfig stamp: reconfig=RttHop|Flicker on observe (SoftFlicker review-only)."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import HOUSE_ENDPOINT_CUT, RECONFIG_KINDS

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(body: str) -> str:
    return f"""
lang vela 0.1
controller Probe {{
{body}
{LOSS}
}}
"""


class TestReconfigStamp(unittest.TestCase):
    def test_kinds_constant_is_rtthop_flicker(self):
        self.assertEqual(RECONFIG_KINDS, ("RttHop", "Flicker"))
        self.assertEqual("|".join(RECONFIG_KINDS), "RttHop|Flicker")

    def test_house_cut_not_retuned(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_kinded_match_stamps_reconfig_kinds(self):
        src = _src(
            """
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
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
        res = check(parse(src, "kinded.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.typed_reconfig)
        self.assertEqual(res.reconfig_kinds, "RttHop|Flicker")
        self.assertTrue(res.observe_only)
        self.assertNotIn("SoftFlicker", res.closed_writes)

    def test_missing_flicker_no_stamp(self):
        src = _src(
            """
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
  }
"""
        )
        res = check(parse(src, "hop-only.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.typed_reconfig)
        self.assertEqual(res.reconfig_kinds, "")

    def test_bare_reconfig_no_stamp(self):
        src = _src(
            """
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) {
    invalidate min_rtt, bw
    enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
  }
"""
        )
        res = check(parse(src, "bare.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.typed_reconfig)
        self.assertEqual(res.reconfig_kinds, "")

    def test_cli_reach_prints_kinded_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = vela_main(["check", str(EX / "reach.vela")])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("reconfig=RttHop|Flicker", out)
        self.assertIn("kinded match required", out)
        self.assertIn("SoftFlicker review-only", out)
        self.assertNotIn("reconfig=RttHop|Flicker  (house cut 0.58)", out)

    def test_cli_horizon_prints_kinded_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = vela_main(["check", str(EX / "horizon.vela")])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("reconfig=RttHop|Flicker", out)
        self.assertIn("kinded match required", out)
        self.assertIn("SoftFlicker review-only", out)

    def test_softflicker_example_is_review_only(self):
        text = (EX / "reach_softflicker.vela").read_text(encoding="utf-8")
        res = check(parse(text, "reach_softflicker.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.posture, "review")
        self.assertIn("SoftFlicker", res.closed_writes)
        self.assertFalse(res.observe_only)

    def test_docs_name_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        eq = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("reconfig=RttHop|Flicker", lang)
        self.assertIn("kinded match required", lang)
        self.assertIn("SoftFlicker review-only", lang)
        self.assertIn("do not retune 0.58", lang)
        self.assertIn("reconfig=RttHop|Flicker", eq)
        self.assertIn("SoftFlicker review-only", eq)
        self.assertIn("0.58", eq)


if __name__ == "__main__":
    unittest.main()
