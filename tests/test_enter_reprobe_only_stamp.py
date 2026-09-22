"""enter=Reprobe-only stamp: enter-location law visible on vela check.

Only enter Reprobe is legal; enter Cruise is a type error. SoftReprobe
house cut stays 0.58. Observe-only. No Detect fork, no closed-write, no
dish Mbps.
"""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check, hybrid_unknown_mode_error
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import (
    ENTER_REPROBE_ONLY_CHECK_LINE,
    ENTER_REPROBE_ONLY_STAMP,
    HOUSE_ENDPOINT_CUT,
    HYBRID_MODES,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(body: str, *, posture: str = "review") -> str:
    return f"""
lang vela 0.4
controller Probe {{
  posture {posture}
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
{body}
{LOSS}
}}
"""


class TestEnterReprobeOnlyConstants(unittest.TestCase):
    def test_stamp_is_explicit_key_value(self):
        self.assertEqual(ENTER_REPROBE_ONLY_STAMP, "enter=Reprobe-only")
        self.assertTrue(
            ENTER_REPROBE_ONLY_CHECK_LINE.startswith("enter=Reprobe-only")
        )
        self.assertIn("Cruise", ENTER_REPROBE_ONLY_CHECK_LINE)
        self.assertIn("type error", ENTER_REPROBE_ONLY_CHECK_LINE)
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)
        self.assertEqual(HYBRID_MODES, frozenset({"Reprobe"}))


class TestEnterReprobeOnlyStamp(unittest.TestCase):
    def test_reach_is_hybrid_enter_ok(self):
        res = check(
            parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hybrid)

    def test_equinox_is_hybrid_enter_ok(self):
        res = check(
            parse(
                (EX / "equinox.vela").read_text(encoding="utf-8"), "equinox.vela"
            )
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hybrid)

    def test_reach_check_prints_enter_reprobe_only(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(ENTER_REPROBE_ONLY_CHECK_LINE, out)
        self.assertIn("enter=Reprobe-only", out)
        self.assertIn("enter Cruise is a type error", out)
        self.assertIn("0.58", out)

    def test_equinox_check_prints_enter_reprobe_only(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(ENTER_REPROBE_ONLY_CHECK_LINE, out)
        self.assertIn("enter=Reprobe-only", out)

    def test_ascent_check_prints_enter_reprobe_only(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "ascent.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(ENTER_REPROBE_ONLY_CHECK_LINE, out)

    def test_enter_reprobe_in_on_is_legal(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => enter Reprobe(cut: 0.58)
    Flicker => enter Reprobe(cut: 0.58)
  }
"""
        )
        res = check(parse(src, "enter-reprobe.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hybrid)

    def test_enter_cruise_is_type_error(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => enter Cruise
    Flicker => enter Reprobe(cut: 0.58)
  }
"""
        )
        res = check(parse(src, "enter-cruise.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertIn(hybrid_unknown_mode_error("Probe", "Cruise"), res.errors)

    def test_docs_name_enter_reprobe_only_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        eq = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("enter=Reprobe-only", lang)
        self.assertIn("enter Cruise", lang)
        self.assertIn("enter=Reprobe-only", eq)
        self.assertIn("Enter location", eq)


if __name__ == "__main__":
    unittest.main()
