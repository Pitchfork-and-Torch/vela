"""Equinox level-vs-integrator honesty: stamp integrator=level on check."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check, integrator_level_line
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import INTEGRATOR_LEVEL_STAMP

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
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    p_ho: Prob
  on Reconfig(e) match e {{
    RttHop => {{
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }}
    Flicker => {{
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }}
  }}
{LOSS}
{body}
}}
"""


class TestIntegratorLevelStamp(unittest.TestCase):
    def test_constant_and_line(self):
        self.assertEqual(INTEGRATOR_LEVEL_STAMP, "level")
        self.assertIn("integrator=level", integrator_level_line())
        self.assertIn("pace*=", integrator_level_line())

    def test_ok_program_stamps_level(self):
        src = _src("  when p_ho > 0.55 {\n    freeze min_rtt, bw for 1.4 * rtt\n  }\n")
        res = check(parse(src, "ok.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.integrator, "level")

    def test_bare_pace_mul_clears_stamp(self):
        src = _src("  when p_ho > 0.35 {\n    pace *= 0.94\n  }\n")
        res = check(parse(src, "bad.vela"))
        self.assertFalse(res.ok)
        self.assertEqual(res.integrator, "")
        self.assertTrue(any("is an integrator" in e for e in res.errors))

    def test_reach_and_horizon_cli(self):
        for name in ("reach.vela", "horizon.vela"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vela_main(["check", str(EX / name)])
            out = buf.getvalue()
            self.assertEqual(rc, 0, out)
            self.assertIn("integrator=level", out)

    def test_docs_name_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("integrator=level", lang)
        self.assertIn("integrator=level", equinox)


if __name__ == "__main__":
    unittest.main()
