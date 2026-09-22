"""Level vs integrator law is a visible vela check stamp."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import LEVEL_VS_INTEGRATOR_CHECK_LINE, LEVEL_VS_INTEGRATOR_STAMP

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


def _src(body: str) -> str:
    return f"""
lang vela 0.4
controller Probe {{
  posture observe
  compose Detect + SoftReprobe + IntervalBw
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
{body}
{LOSS}
}}
"""


class TestLevelVsIntegratorStamp(unittest.TestCase):
    def test_stamp_constants(self):
        self.assertEqual(LEVEL_VS_INTEGRATOR_STAMP, "level_vs_integrator")
        self.assertIn("level_vs_integrator", LEVEL_VS_INTEGRATOR_CHECK_LINE)
        self.assertIn("integrate", LEVEL_VS_INTEGRATOR_CHECK_LINE)

    def test_reach_holds(self):
        res = check(parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.level_vs_integrator)

    def test_equinox_holds(self):
        res = check(
            parse((EX / "equinox.vela").read_text(encoding="utf-8"), "equinox.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.level_vs_integrator)

    def test_reach_cli_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(LEVEL_VS_INTEGRATOR_CHECK_LINE, out)
        self.assertIn("0.58", out)

    def test_equinox_cli_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(LEVEL_VS_INTEGRATOR_CHECK_LINE, out)

    def test_pace_mul_without_integrate_fail_closed(self):
        src = _src(
            """
  when p_ho > 0.35 {
    pace *= 0.94
  }
"""
        )
        res = check(parse(src, "level-fail.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.level_vs_integrator)
        self.assertTrue(any("integrator" in e for e in res.errors), res.errors)

    def test_docs_cite_stamp(self):
        lang = (DOCS / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (DOCS / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("level_vs_integrator", lang)
        self.assertIn("stamps `level_vs_integrator`", equinox)


if __name__ == "__main__":
    unittest.main()
