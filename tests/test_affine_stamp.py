"""Affine Sample freshness law is a visible vela check stamp."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    affine_epoch_error,
    affine_reuse_error,
    check,
)
from vela.cli import main as vela_main
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

STAMP = (
    "affine-samples  (second Sample read refuse; "
    "Sample @ e use-once; e+1 is prior)"
)
OLD_STAMP = "affine  (Sample @ e is use-once; e+1 is prior)"


class TestAffineSamplesStamp(unittest.TestCase):
    def test_reach_is_affine(self):
        res = check(
            parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.affine)

    def test_equinox_is_affine(self):
        res = check(
            parse(
                (EX / "equinox.vela").read_text(encoding="utf-8"), "equinox.vela"
            )
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.affine)

    def test_reach_check_prints_explicit_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(STAMP, out)
        self.assertIn("affine-samples", out)
        self.assertIn("second Sample read refuse", out)
        # Old short stamp must not remain the visible line.
        self.assertNotIn(OLD_STAMP, out)

    def test_equinox_check_prints_explicit_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(STAMP, out)
        self.assertIn("affine-samples", out)
        self.assertIn("second Sample read refuse", out)
        self.assertNotIn(OLD_STAMP, out)

    def test_ascent_check_prints_explicit_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "ascent.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(STAMP, out)

    def test_second_sample_read_refused(self):
        src = """
lang vela 0.1
controller Probe {
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      let a = rtt
      let b = rtt
    }
    Flicker => hold
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "second-read.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.affine)
        self.assertIn(affine_reuse_error("Probe", "rtt"), res.errors)

    def test_sample_after_reprobe_refused(self):
        src = """
lang vela 0.1
controller Probe {
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58)
      let x = rtt
    }
    Flicker => hold
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "eplus1.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.affine)
        self.assertIn(affine_epoch_error("Probe", "rtt"), res.errors)

    def test_docs_name_visible_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        for doc in (lang, equinox):
            self.assertIn("affine-samples", doc)
            self.assertIn("second Sample read refuse", doc)
        self.assertIn("Affine samples", equinox)
        self.assertIn("prior.rtt", equinox)


if __name__ == "__main__":
    unittest.main()
