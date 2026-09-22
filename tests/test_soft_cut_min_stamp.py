"""Soft-cut min law is a visible vela check stamp when SoftFlicker+SoftReprobe."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.compose import apply_composed_cut, compose_soft_cuts
from vela.parser import parse
from vela.types import HOUSE_ENDPOINT_CUT

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

STAMP = (
    "soft-cut-min  (compose cuts = min; SoftFlicker 0.85 cannot raise after 0.58)"
)

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(compose: str, *, posture: str = "review") -> str:
    return f"""
lang vela 0.4
controller Probe {{
  posture {posture}
  compose {compose}
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
  on Reconfig(e) {{
    invalidate min_rtt, bw
    enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
  }}
{LOSS}
}}
"""


class TestSoftCutMinStamp(unittest.TestCase):
    def test_house_cut_untouched(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_runtime_min_softflicker_cannot_raise(self):
        self.assertEqual(compose_soft_cuts([0.58, 0.85]), 0.58)
        before = 12000.0
        self.assertAlmostEqual(
            apply_composed_cut(before, [0.58, 0.85]), before * 0.58
        )

    def test_softflicker_with_softreprobe_stamps(self):
        src = _src("Detect + SoftReprobe + SoftFlicker")
        res = check(parse(src, "softflicker.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.soft_cut_min)
        self.assertEqual(res.closed_writes, ["SoftFlicker"])
        self.assertFalse(res.observe_only)

    def test_softreprobe_alone_no_stamp(self):
        src = _src("Detect + SoftReprobe", posture="observe")
        # observe SoftReprobe alone needs typed reconfig/loss already in _src;
        # bare Reconfig fails observe. Use review SoftReprobe-only.
        src = _src("Detect + SoftReprobe", posture="review")
        res = check(parse(src, "reprobe-only.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.soft_cut_min)

    def test_reach_no_softflicker_no_stamp(self):
        res = check(
            parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.soft_cut_min)
        self.assertTrue(res.observe_only)

    def test_cli_prints_stamp_for_softflicker_compose(self):
        src = _src("Detect + SoftReprobe + SoftFlicker")
        path = ROOT / "examples" / "_tmp_softcut_min_stamp.vela"
        try:
            path.write_text(src, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vela_main(["check", str(path)])
            out = buf.getvalue()
            self.assertEqual(rc, 0, out)
            self.assertIn(STAMP, out)
            self.assertIn("soft-cut-min", out)
            self.assertIn("compose cuts = min", out)
            self.assertIn("SoftFlicker 0.85 cannot raise after 0.58", out)
            # Do not retune SoftReprobe / house cut.
            self.assertIn("0.58", out)
            self.assertNotIn("house_endpoint_cut=0.85", out)
        finally:
            if path.exists():
                path.unlink()

    def test_reach_check_omits_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("soft-cut-min", out)
        # SoftReprobe house cut stays named on reconfig gloss; not retuned.
        self.assertIn("house cut 0.58", out)

    def test_docs_name_visible_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        ingress = (ROOT / "docs" / "INGRESS.md").read_text(encoding="utf-8")
        for doc in (lang, equinox, ingress):
            self.assertIn("soft-cut-min", doc)
            self.assertIn("compose cuts = min", doc)
            self.assertIn("0.58", doc)
            self.assertIn("0.85", doc)


if __name__ == "__main__":
    unittest.main()
