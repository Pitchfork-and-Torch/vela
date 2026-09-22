"""posture=observe stamp: Reach check honesty + review-no-closed-write warn.

Visible flagship stamp. SoftReprobe house cut stays 0.58. No Detect fork,
no closed-write enable, no dish Mbps.
"""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    check,
    review_closed_write_warning,
    review_no_closed_write_warning,
)
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import (
    HOUSE_ENDPOINT_CUT,
    POSTURE_OBSERVE_CHECK_LINE,
    POSTURE_OBSERVE_STAMP,
    POSTURE_REVIEW_CHECK_LINE,
    POSTURE_REVIEW_STAMP,
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


def _src(body: str) -> str:
    return f"""
lang vela 0.1
controller Probe {{
{body}
{LOSS}
}}
"""


class TestPostureStampConstants(unittest.TestCase):
    def test_stamps_are_explicit_key_value(self):
        self.assertEqual(POSTURE_OBSERVE_STAMP, "posture=observe")
        self.assertEqual(POSTURE_REVIEW_STAMP, "posture=review")
        self.assertTrue(POSTURE_OBSERVE_CHECK_LINE.startswith("posture=observe"))
        self.assertIn("flagship", POSTURE_OBSERVE_CHECK_LINE)
        self.assertIn("no closed-write", POSTURE_OBSERVE_CHECK_LINE)
        self.assertTrue(POSTURE_REVIEW_CHECK_LINE.startswith("posture=review"))
        self.assertIn("ablation", POSTURE_REVIEW_CHECK_LINE)
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)


class TestReachPostureStamp(unittest.TestCase):
    def test_reach_check_result_is_observe(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.posture, "observe")
        self.assertTrue(res.observe_only)
        self.assertEqual(res.closed_writes, [])

    def test_reach_cli_prints_posture_observe(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(POSTURE_OBSERVE_CHECK_LINE, out)
        self.assertIn("posture=observe", out)
        self.assertIn("observe-only", out)
        self.assertIn("0.58", out)
        self.assertNotIn("posture=review", out)

    def test_equinox_cli_prints_posture_observe(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(POSTURE_OBSERVE_CHECK_LINE, out)


class TestReviewNoClosedWriteWarn(unittest.TestCase):
    def test_helper_names_flagship_observe(self):
        msg = review_no_closed_write_warning("Probe")
        self.assertIn("posture review with no closed-write", msg)
        self.assertIn("flagship Reach is observe", msg)

    def test_review_with_writes_helper(self):
        msg = review_closed_write_warning("Probe", ["QuietReach"])
        self.assertIn("ablation only", msg)
        self.assertIn("QuietReach", msg)

    def test_review_no_closed_write_warns(self):
        src = _src(
            """
  posture review
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
"""
        )
        res = check(parse(src, "review-empty.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.posture, "review")
        self.assertFalse(res.observe_only)
        self.assertEqual(res.closed_writes, [])
        self.assertIn(review_no_closed_write_warning("Probe"), res.warnings)

    def test_cli_surfaces_review_no_closed_write_warning(self):
        path = ROOT / "tests" / "_tmp_review_no_cw.vela"
        path.write_text(
            _src(
                """
  posture review
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
"""
            ),
            encoding="utf-8",
            newline="\n",
        )
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vela_main(["check", str(path)])
            out = buf.getvalue()
            self.assertEqual(rc, 0, out)
            self.assertIn("warning:", out)
            self.assertIn("no closed-write", out)
            self.assertIn(POSTURE_REVIEW_CHECK_LINE, out)
            self.assertIn("posture=review", out)
            self.assertNotIn("posture=observe", out)
        finally:
            path.unlink(missing_ok=True)


class TestDocsPostureStamp(unittest.TestCase):
    def test_language_names_posture_observe_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("`posture=observe`", lang)
        self.assertIn("no closed-write operator warns", lang)

    def test_ingress_requires_posture_observe(self):
        ingress = (ROOT / "docs" / "INGRESS.md").read_text(encoding="utf-8")
        self.assertIn("`posture=observe`", ingress)


if __name__ == "__main__":
    unittest.main()
