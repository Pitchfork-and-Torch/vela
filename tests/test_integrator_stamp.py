"""integrator=level stamp: when/every *= needs integrate (not per-ACK).

SoftReprobe house cut stays 0.58. No Detect fork, no closed-write, no dish Mbps.
"""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import (
    HOUSE_ENDPOINT_CUT,
    INTEGRATOR_CHECK_LINE,
    INTEGRATOR_OPS,
    INTEGRATOR_STAMP,
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


class TestIntegratorStampConstants(unittest.TestCase):
    def test_stamp_names_level(self):
        self.assertEqual(INTEGRATOR_STAMP, "integrator=level")
        self.assertTrue(INTEGRATOR_CHECK_LINE.startswith("integrator=level"))
        self.assertIn("needs integrate", INTEGRATOR_CHECK_LINE)
        self.assertIn("*=", INTEGRATOR_OPS)
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)


class TestReachIntegratorStamp(unittest.TestCase):
    def test_reach_check_result_integrator_true(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.integrator)
        self.assertTrue(res.observe_only)

    def test_reach_cli_prints_integrator_level(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(INTEGRATOR_CHECK_LINE, out)
        self.assertIn("integrator=level", out)
        self.assertIn("0.58", out)
        self.assertIn("observe-only", out)

    def test_equinox_cli_prints_integrator_level(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(INTEGRATOR_CHECK_LINE, out)


class TestIntegratorRefuseClearsStamp(unittest.TestCase):
    def test_bare_when_scale_refuses_and_clears(self):
        src = f"""
lang vela 0.1
controller Probe {{
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  when p_ho > 0.35 {{
    pace *= 0.94
  }}
{LOSS}
}}
"""
        res = check(parse(src, "bare-integr.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.integrator)
        self.assertTrue(any("integrator" in e for e in res.errors))

    def test_integrate_when_opts_in_keeps_stamp(self):
        src = """
lang vela 0.3
controller Risky {
  posture review
  compose Detect
  signals:
    epoch: Epoch
  integrate when p_ho > 0.35 {
    pace *= 0.94
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "opt-in.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.integrator)
        self.assertTrue(any("integrate when" in w for w in res.warnings))


class TestIntegratorDocs(unittest.TestCase):
    def test_language_names_stamp(self):
        text = (DOCS / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("integrator=level", text)
        self.assertIn("Level vs integrator", text)

    def test_ingress_names_stamp(self):
        text = (DOCS / "INGRESS.md").read_text(encoding="utf-8")
        self.assertIn("integrator=level", text)


if __name__ == "__main__":
    unittest.main()
