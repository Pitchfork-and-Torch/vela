"""Level vs integrator: integrator=refuse is a visible vela check stamp."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


class TestIntegratorRefuseStamp(unittest.TestCase):
    def test_reach_stamps_refuse(self):
        res = check(parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.integrator_refuse)

    def test_equinox_stamps_refuse(self):
        res = check(
            parse((EX / "equinox.vela").read_text(encoding="utf-8"), "equinox.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.integrator_refuse)

    def test_integrate_when_opts_in_clears_stamp(self):
        src = f"""
lang vela 0.3
controller Risky {{
  posture review
  compose Detect
  signals:
    epoch: Epoch
  integrate when p_ho > 0.35 {{
    pace *= 0.94
  }}
{LOSS}
}}
"""
        res = check(parse(src, "risky.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.integrator_refuse)
        self.assertTrue(any("integrate when" in w for w in res.warnings))

    def test_unguarded_integrator_errors_and_keeps_refuse(self):
        src = f"""
lang vela 0.3
controller Bad {{
  posture review
  compose Detect
  signals:
    epoch: Epoch
  when p_ho > 0.35 {{
    pace *= 0.94
  }}
{LOSS}
}}
"""
        res = check(parse(src, "bad.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(res.integrator_refuse)
        self.assertTrue(any("integrator" in e for e in res.errors))

    def test_reach_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("integrator=refuse", out)
        self.assertIn("pace*=k needs integrate when", out)
        self.assertIn("0.58", out)

    def test_equinox_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("integrator=refuse", out)

    def test_docs_name_visible_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("integrator=refuse", lang)
        self.assertIn("integrator=refuse", equinox)
        self.assertIn("0.58", equinox)


if __name__ == "__main__":
    unittest.main()
