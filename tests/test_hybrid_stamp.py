"""Hybrid automata law is a visible vela check stamp."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    check,
    hybrid_jump_in_flow_error,
    hybrid_tick_error,
)
from vela.cli import main as vela_main
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

STAMP = (
    "hybrid-automata  (enter/invalidate/cut only in on-handlers; "
    "every tick ack|epoch)"
)
OLD_STAMP = "hybrid  (on = jump; when/every = flow)"

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


class TestHybridAutomataStamp(unittest.TestCase):
    def test_reach_is_hybrid(self):
        res = check(
            parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hybrid)

    def test_equinox_is_hybrid(self):
        res = check(
            parse(
                (EX / "equinox.vela").read_text(encoding="utf-8"), "equinox.vela"
            )
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hybrid)

    def test_reach_check_prints_explicit_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(STAMP, out)
        self.assertIn("hybrid-automata", out)
        self.assertIn("enter/invalidate/cut only in on-handlers", out)
        self.assertIn("every tick ack|epoch", out)
        self.assertNotIn(OLD_STAMP, out)

    def test_equinox_check_prints_explicit_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(STAMP, out)
        self.assertIn("hybrid-automata", out)
        self.assertIn("enter/invalidate/cut only in on-handlers", out)
        self.assertNotIn(OLD_STAMP, out)

    def test_ascent_check_prints_explicit_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "ascent.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(STAMP, out)

    def test_enter_in_when_refused(self):
        src = _src(
            """
  when p_ho > 0.5 {
    enter Reprobe(cut: 0.58)
  }
"""
        )
        res = check(parse(src, "enter-when.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertIn(
            hybrid_jump_in_flow_error("Probe", "enter Reprobe", "when"),
            res.errors,
        )

    def test_cut_in_every_refused(self):
        src = _src(
            """
  every ack {
    cut(0.72)
  }
"""
        )
        res = check(parse(src, "cut-every.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertIn(
            hybrid_jump_in_flow_error("Probe", "cut", "every"),
            res.errors,
        )

    def test_every_rtt_tick_refused(self):
        src = _src(
            """
  every rtt {
    hold
  }
"""
        )
        res = check(parse(src, "every-rtt.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertIn(hybrid_tick_error("Probe", "rtt"), res.errors)

    def test_docs_name_visible_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        for doc in (lang, equinox):
            self.assertIn("hybrid-automata", doc)
            self.assertIn("enter/invalidate/cut only in on-handlers", doc)
            self.assertIn("every tick ack|epoch", doc)
        self.assertIn("Hybrid automata", equinox)
        self.assertIn("on-handlers", equinox)


if __name__ == "__main__":
    unittest.main()
