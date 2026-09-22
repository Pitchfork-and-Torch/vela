"""ASCENT hint ingress: fail-closed compose examples + docs surface."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check
from vela.cli import main
from vela.parser import parse
import io
from contextlib import redirect_stdout


ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
DOCS = ROOT / "docs"


class TestAscentIngress(unittest.TestCase):
    def test_ascent_example_is_fail_closed_observe(self):
        src = (EX / "ascent.vela").read_text(encoding="utf-8")
        res = check(parse(src, "ascent.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.observe_only)
        self.assertTrue(res.hint_fail_closed)
        self.assertTrue(res.passthrough)

    def test_ascent_erased_example_holds_on_none(self):
        src = (EX / "ascent_erased.vela").read_text(encoding="utf-8")
        self.assertIn("None => hold", src)
        self.assertNotIn("cut(", src.split("on Hint")[1].split("}")[0])
        res = check(parse(src, "ascent_erased.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hint_fail_closed)
        self.assertTrue(res.observe_only)

    def test_reach_stays_defined_without_hint_use(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        self.assertNotIn("std.hint", src)
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.hint_fail_closed)

    def test_check_cli_prints_hint_fail_closed_for_ascent(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", str(EX / "ascent.vela")])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("hint=fail-closed", out)
        self.assertIn("observe-only", out)

    def test_ingress_docs_name_both_compose_examples(self):
        text = (DOCS / "INGRESS.md").read_text(encoding="utf-8")
        self.assertIn("ascent.vela", text)
        self.assertIn("ascent_erased.vela", text)
        self.assertIn("fail-closed", text.lower())


if __name__ == "__main__":
    unittest.main()
