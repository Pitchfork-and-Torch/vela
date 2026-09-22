"""use=named-only stamp: unknown use is type error; no import *.

Visible on vela check. SoftReprobe house cut stays 0.58. Observe-only.
No Detect fork, no closed-write, no dish Mbps.
"""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check, use_named_only_check_line
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import (
    HOUSE_ENDPOINT_CUT,
    STDLIB_MODULES,
    USE_NAMED_ONLY_CHECK_LINE,
    USE_NAMED_ONLY_STAMP,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def _prog(uses: list[str]) -> str:
    use_lines = "\n".join(f"use {u}" for u in uses)
    return f"""
lang vela 0.1
{use_lines}
controller Probe {{
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {{
    RttHop => hold
    Flicker => hold
  }}
  on Loss(k) match k {{
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }}
}}
"""


class TestUseNamedOnlyConstants(unittest.TestCase):
    def test_stamp_constants(self):
        self.assertEqual(USE_NAMED_ONLY_STAMP, "use=named-only")
        self.assertEqual(
            USE_NAMED_ONLY_CHECK_LINE,
            use_named_only_check_line(USE_NAMED_ONLY_STAMP),
        )
        self.assertIn("type error", USE_NAMED_ONLY_CHECK_LINE)
        self.assertIn("import *", USE_NAMED_ONLY_CHECK_LINE)
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)
        self.assertIn("std.path", STDLIB_MODULES)


class TestUseNamedOnlyStamp(unittest.TestCase):
    def test_reach_stamps_named_only(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.use_named_only, USE_NAMED_ONLY_STAMP)
        self.assertEqual(res.posture, "observe")

    def test_reach_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(USE_NAMED_ONLY_CHECK_LINE, out)
        self.assertIn("use=named-only", out)
        self.assertNotIn("Mbps", USE_NAMED_ONLY_CHECK_LINE)

    def test_equinox_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(USE_NAMED_ONLY_CHECK_LINE, out)

    def test_unknown_use_is_type_error(self):
        src = _prog(["std.path", "std.not_a_module"])
        res = check(parse(src, "bad-use.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("unknown module" in e for e in res.errors),
            res.errors,
        )
        self.assertEqual(res.use_named_only, "")

    def test_named_stdlib_uses_ok(self):
        src = _prog(["std.path", "std.eval"])
        res = check(parse(src, "named.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.use_named_only, USE_NAMED_ONLY_STAMP)

    def test_wildcard_use_refused(self):
        # Parser may not accept bare *; inject via Program when possible.
        from vela.ast import Program, Controller

        prog = parse(_prog(["std.path"]), "star.vela")
        prog.uses.append("*")
        res = check(prog)
        self.assertFalse(res.ok)
        self.assertTrue(
            any("wildcard" in e or "import *" in e for e in res.errors),
            res.errors,
        )
        self.assertEqual(res.use_named_only, "")

    def test_docs_mention_law(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("use=named-only", lang)
        notes = (ROOT / "docs" / "EVAL-NOTES.md").read_text(encoding="utf-8")
        self.assertIn("use=named-only", notes)


if __name__ == "__main__":
    unittest.main()
