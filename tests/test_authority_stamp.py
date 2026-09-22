"""Authority stamp: authority=absent|budget visible on vela check."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import (
    AUTHORITY_ABSENT_CHECK_LINE,
    AUTHORITY_ABSENT_STAMP,
    AUTHORITY_BUDGET_CHECK_LINE,
    AUTHORITY_BUDGET_STAMP,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


class TestAuthorityStamp(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(AUTHORITY_ABSENT_STAMP, "authority=absent")
        self.assertEqual(AUTHORITY_BUDGET_STAMP, "authority=budget")
        self.assertIn("authority=absent", AUTHORITY_ABSENT_CHECK_LINE)
        self.assertIn("authority=budget", AUTHORITY_BUDGET_CHECK_LINE)

    def test_reach_absent(self):
        res = check(parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.authority_stamp, "absent")
        self.assertFalse(res.authority)

    def test_equinox_budget(self):
        res = check(
            parse((EX / "equinox.vela").read_text(encoding="utf-8"), "equinox.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.authority_stamp, "budget")
        self.assertTrue(res.authority)

    def test_reach_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("authority=absent", out)
        self.assertIn("0.58", out)

    def test_equinox_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("authority=budget", out)
        self.assertIn("0.58", out)

    def test_docs_name_visible_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertTrue("authority=absent" in lang or "authority=budget" in lang)
        self.assertTrue("authority=absent" in equinox or "authority=budget" in equinox)
        self.assertIn("0.58", equinox)


if __name__ == "__main__":
    unittest.main()
