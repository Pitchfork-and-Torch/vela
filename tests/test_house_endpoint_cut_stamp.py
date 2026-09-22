"""SoftReprobe / house endpoint cut 0.58 is a visible vela check stamp."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import HOUSE_ENDPOINT_CUT

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


class TestHouseEndpointCutStamp(unittest.TestCase):
    def test_constant_is_load_bearing_058(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_softreprobe_compose_stamps_cut(self):
        src = _src(
            """
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
    Flicker => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
  }
"""
        )
        res = check(parse(src, "with-soft.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.house_endpoint_cut, HOUSE_ENDPOINT_CUT)
        self.assertEqual(res.house_endpoint_cut, 0.58)

    def test_without_softreprobe_no_stamp(self):
        src = _src(
            """
  posture observe
  compose Detect
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
    Flicker => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
  }
"""
        )
        res = check(parse(src, "no-soft.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertIsNone(res.house_endpoint_cut)

    def test_reach_check_prints_both_stamps(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("house_endpoint_cut=0.58", out)
        self.assertIn("softreprobe_cut=0.58", out)

    def test_horizon_check_prints_both_stamps(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "horizon.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("house_endpoint_cut=0.58", out)
        self.assertIn("softreprobe_cut=0.58", out)

    def test_docs_name_visible_stamps(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("house_endpoint_cut=0.58", lang)
        self.assertIn("softreprobe_cut=0.58", lang)
        self.assertIn("house_endpoint_cut=0.58", equinox)
        self.assertIn("softreprobe_cut=0.58", equinox)
        self.assertIn("do not retune", lang.lower())
        self.assertIn("do not retune", equinox.lower())


if __name__ == "__main__":
    unittest.main()
