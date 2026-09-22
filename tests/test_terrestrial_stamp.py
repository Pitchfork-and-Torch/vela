"""Forgotten terrestrial floor is a check stamp. INCOMPLETE is never ACCEPT."""
from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from vela.checker import check, terrestrial_check_line
from vela.cli import main
from vela.parser import parse
from vela.types import HOUSE_ENDPOINT_CUT

EX = Path(__file__).resolve().parents[1] / "examples"


def _prog(*, floor: bool) -> str:
    terr = "  assert terrestrial.goodput >= 77 Mbps\n" if floor else ""
    return f"""
lang vela 0.1
use std.path
use std.eval
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
path LeoFastHO {{
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}}
contract DualGate vs BBR {{
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  assert mean(goodput) >= 1
{terr}}}
"""


def _check_stdout(path: Path) -> tuple[int, str]:
    buf = StringIO()
    with patch("sys.stdout", buf):
        rc = main(["check", str(path)])
    return rc, buf.getvalue()


class TestTerrestrialStamp(unittest.TestCase):
    def test_house_cut_stays(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_reach_stamps_named(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.terrestrial, "named")
        self.assertEqual(res.posture, "observe")
        rc, out = _check_stdout(EX / "reach.vela")
        self.assertEqual(rc, 0)
        line = next(ln for ln in out.splitlines() if "terrestrial=" in ln)
        self.assertEqual(line.strip(), terrestrial_check_line("named"))
        self.assertIn("INCOMPLETE", line)
        self.assertIn("FAIL", line)
        self.assertNotIn("Mbps", line)
        self.assertNotIn("ACCEPT", line)

    def test_missing_floor_stamps_incomplete_never_accept(self):
        src = _prog(floor=False)
        res = check(parse(src, "no-terr.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.terrestrial, "missing")
        self.assertTrue(
            any("missing terrestrial assert" in w for w in res.warnings),
            res.warnings,
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "no-terr.vela"
            path.write_text(src, encoding="utf-8", newline="\n")
            rc, out = _check_stdout(path)
        self.assertEqual(rc, 0)
        line = next(ln for ln in out.splitlines() if "terrestrial=" in ln)
        self.assertEqual(line.strip(), terrestrial_check_line("missing"))
        self.assertIn("INCOMPLETE", line)
        self.assertIn("never ACCEPT", line)
        self.assertNotIn("Mbps", line)

    def test_named_floor_on_synthetic(self):
        res = check(parse(_prog(floor=True), "with-terr.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.terrestrial, "named")

    def test_one_forgotten_contract_stamps_missing(self):
        src = _prog(floor=True) + """
contract Side vs BBR {
  seeds = [13, 7]
  scenario leo_fast_ho duration 90s
  assert mean(goodput) >= 1
}
"""
        res = check(parse(src, "half.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.terrestrial, "missing")

    def test_no_contract_is_unstamped(self):
        src = """
lang vela 0.1
controller Probe {
  compose Detect
}
"""
        res = check(parse(src, "bare.vela"))
        self.assertEqual(res.terrestrial, "")
        self.assertEqual(terrestrial_check_line(""), "")
        self.assertEqual(terrestrial_check_line("other"), "")


if __name__ == "__main__":
    unittest.main()
