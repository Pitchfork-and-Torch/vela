"""hint=Some|None stamp: visible Option-match fail-closed on check.

Bare hint.ascent in arithmetic is illegal; use std.hint is required.
SoftReprobe house cut stays 0.58. No Detect fork, no closed-write, no dish Mbps.
"""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check, hint_law_error
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import (
    HINT_ARMS,
    HINT_OPTION_CHECK_LINE,
    HINT_OPTION_STAMP,
    HOUSE_ENDPOINT_CUT,
)

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


def _src(uses: str, body: str) -> str:
    return f"""
lang vela 0.1
{uses}
controller Probe {{
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    hint: Hint<PathHint>
{body}
{LOSS}
}}
"""


class TestHintOptionStampConstants(unittest.TestCase):
    def test_stamp_names_match_arms(self):
        self.assertEqual(HINT_OPTION_STAMP, "hint=Some|None")
        self.assertEqual(HINT_ARMS, ("Some", "None"))
        self.assertTrue(HINT_OPTION_CHECK_LINE.startswith("hint=Some|None"))
        self.assertIn("fail-closed", HINT_OPTION_CHECK_LINE)
        self.assertIn("missing is None", HINT_OPTION_CHECK_LINE)
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_old_fail_closed_token_is_retired(self):
        self.assertNotEqual(HINT_OPTION_STAMP, "hint=fail-closed")
        self.assertNotIn("hint=fail-closed", HINT_OPTION_CHECK_LINE)


class TestAscentHintOptionStamp(unittest.TestCase):
    def test_ascent_check_result_sets_hint_fail_closed(self):
        src = (EX / "ascent.vela").read_text(encoding="utf-8")
        res = check(parse(src, "ascent.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hint_fail_closed)
        self.assertTrue(res.observe_only)

    def test_ascent_cli_prints_hint_some_none(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "ascent.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(HINT_OPTION_CHECK_LINE, out)
        self.assertIn("hint=Some|None", out)
        self.assertNotIn("hint=fail-closed", out)
        self.assertIn("0.58", out)

    def test_reach_cli_omits_hint_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("hint=Some|None", out)
        self.assertNotIn("hint=fail-closed", out)
        self.assertIn("0.58", out)
        self.assertIn("observe-only", out)


class TestHintOptionEnforcement(unittest.TestCase):
    def test_on_hint_must_match_some_none(self):
        src = _src(
            "use std.hint",
            """
  on Hint(h) {
    freeze min_rtt, bw
  }
""",
        )
        res = check(parse(src, "hint-bare.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("Some | None" in e for e in res.errors))

    def test_bare_hint_ascent_arithmetic_illegal(self):
        src = _src(
            "use std.hint",
            """
  every ack {
    let x = hint.ascent
  }
""",
        )
        res = check(parse(src, "bare-hint.vela"))
        self.assertFalse(res.ok)
        self.assertIn(hint_law_error("Probe", "hint"), res.errors)

    def test_use_std_hint_required(self):
        src = _src(
            "",
            """
  on Hint(h) match h {
    Some => hold
    None => hold
  }
""",
        )
        res = check(parse(src, "no-use.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("use std.hint" in e for e in res.errors))

    def test_full_match_stamps_hint_fail_closed(self):
        src = _src(
            "use std.hint",
            """
  on Hint(h) match h {
    Some => hold
    None => hold
  }
""",
        )
        res = check(parse(src, "hint-match.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hint_fail_closed)


class TestHintOptionDocs(unittest.TestCase):
    def test_language_names_hint_some_none_stamp(self):
        text = (DOCS / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("hint=Some|None", text)
        self.assertIn("bare `hint.ascent` in arithmetic is illegal", text)
        self.assertIn("`use std.hint` is required", text)

    def test_ingress_names_ascent_stamp(self):
        text = (DOCS / "INGRESS.md").read_text(encoding="utf-8")
        self.assertIn("hint=Some|None", text)
        self.assertIn("ascent.vela", text)


if __name__ == "__main__":
    unittest.main()
