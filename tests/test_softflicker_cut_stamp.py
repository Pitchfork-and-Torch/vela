"""SoftFlicker alone stamps softflicker_cut=0.85; does not raise SoftReprobe."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import HOUSE_ENDPOINT_CUT, SOFT_FLICKER_CUT

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

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


class TestSoftFlickerCutStamp(unittest.TestCase):
    def test_constants_load_bearing(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)
        self.assertEqual(SOFT_FLICKER_CUT, 0.85)

    def test_softflicker_alone_stamps(self):
        src = _src("Detect + SoftFlicker")
        res = check(parse(src, "sf-alone.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.softflicker_cut, SOFT_FLICKER_CUT)
        self.assertEqual(res.softflicker_cut, 0.85)
        self.assertEqual(res.closed_writes, ["SoftFlicker"])
        self.assertFalse(res.observe_only)

    def test_softflicker_with_softreprobe_no_alone_stamp(self):
        # SoftFlicker+SoftReprobe is soft-cut-min territory, not this stamp.
        src = _src("Detect + SoftReprobe + SoftFlicker")
        res = check(parse(src, "sf-with-sr.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertIsNone(res.softflicker_cut)
        self.assertEqual(res.closed_writes, ["SoftFlicker"])

    def test_softreprobe_alone_no_stamp(self):
        src = _src("Detect + SoftReprobe", posture="review")
        res = check(parse(src, "sr-alone.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertIsNone(res.softflicker_cut)

    def test_reach_observe_no_stamp(self):
        res = check(
            parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertIsNone(res.softflicker_cut)
        self.assertTrue(res.observe_only)

    def test_reach_softflicker_example_has_softreprobe_no_alone_stamp(self):
        res = check(
            parse(
                (EX / "reach_softflicker.vela").read_text(encoding="utf-8"),
                "reach_softflicker.vela",
            )
        )
        self.assertTrue(res.ok, res.errors)
        self.assertIn("SoftFlicker", res.closed_writes)
        self.assertIsNone(res.softflicker_cut)

    def test_cli_prints_stamp_for_softflicker_alone(self):
        src = _src("Detect + SoftFlicker")
        path = ROOT / "examples" / "_tmp_softflicker_cut_stamp.vela"
        try:
            path.write_text(src, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vela_main(["check", str(path)])
            out = buf.getvalue()
            self.assertEqual(rc, 0, out)
            self.assertIn("softflicker_cut=0.85", out)
            self.assertIn("does not raise SoftReprobe", out)
            # Do not retune SoftReprobe / house cut via this stamp.
            self.assertNotIn("house_endpoint_cut=0.85", out)
            self.assertNotIn("softreprobe_cut=0.85", out)
        finally:
            if path.exists():
                path.unlink()

    def test_reach_check_omits_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("softflicker_cut=", out)
        self.assertIn("house cut 0.58", out)

    def test_docs_name_visible_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        for doc in (lang, equinox):
            self.assertIn("softflicker_cut=0.85", doc)
            self.assertIn("does not raise SoftReprobe", doc)
            self.assertIn("0.58", doc)


if __name__ == "__main__":
    unittest.main()
