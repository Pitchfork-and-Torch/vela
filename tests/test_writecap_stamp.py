"""WriteCap / authority stamp on observe flagships (Reach, Equinox)."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    check,
    writecap_ambient_error,
    writecap_exhausted_error,
    writecap_reuse_error,
    writecap_split_sum_error,
    writecap_target_error,
)
from vela.cli import main
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


class TestWriteCapStamp(unittest.TestCase):
    def test_reach_stamps_absent(self):
        res = check(parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.writecap, "absent")
        self.assertEqual(res.authority, {})
        self.assertTrue(res.observe_only)
        self.assertTrue(res.passthrough)

    def test_equinox_stamps_budget_authority_zero(self):
        res = check(
            parse((EX / "equinox.vela").read_text(encoding="utf-8"), "equinox.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.writecap, "budget")
        self.assertEqual(res.authority.get("cwnd"), 0)
        self.assertEqual(res.authority.get("pace"), 0)
        self.assertTrue(res.observe_only)

    def test_cli_reach_prints_absent(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["check", str(EX / "reach.vela")])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("writecap=absent", out)
        self.assertIn("observe flagship", out)
        self.assertNotIn("writecap=budget", out)
        self.assertNotIn("writecap=linear", out)

    def test_cli_equinox_prints_budget_and_authority(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["check", str(EX / "equinox.vela")])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("writecap=budget", out)
        self.assertIn("authority={cwnd:0, pace:0}", out)
        self.assertNotIn("writecap=absent", out)

    def test_absent_does_not_enable_cruise_writes(self):
        # Reach remains observe-only / passthrough; absent is honesty, not a write grant.
        res = check(parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela"))
        self.assertEqual(res.writecap, "absent")
        self.assertTrue(res.observe_only)
        self.assertTrue(res.passthrough)
        self.assertFalse(res.closed_writes)


class TestWriteCapStarlinkDocs(unittest.TestCase):
    def test_error_helpers_name_starlink_epoch(self):
        self.assertIn("Starlink", writecap_exhausted_error("Probe", 1, 0))
        self.assertIn("Starlink", writecap_ambient_error("Probe", "cwnd ="))
        self.assertIn("epoch", writecap_reuse_error("Probe", "cap"))
        self.assertIn("epoch", writecap_split_sum_error("Probe", "cap", 2, 4))
        self.assertIn("Starlink", writecap_target_error("Probe", "cap", "cwnd", "pace"))

    def test_language_docs_absent_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("writecap=absent", lang)
        self.assertIn("writecap=linear", lang)
        self.assertIn("writecap=budget", lang)
        self.assertIn("Starlink", lang)
        # SoftReprobe cut law held in docs
        self.assertIn("0.58", lang)

    def test_equinox_docs_split_borrow_starlink(self):
        eq = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("WriteCap", eq)
        self.assertIn("split", eq)
        self.assertIn("borrow", eq)


if __name__ == "__main__":
    unittest.main()
