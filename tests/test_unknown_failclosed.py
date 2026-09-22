"""Unknown delay gate is fail-closed at check (not advisory)."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import UNKNOWN_DELAY_RATIO

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

RECONFIG = """
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


def _src(loss_body: str) -> str:
    return f"""
lang vela 0.1
controller Probe {{
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    delay_ratio: Ratio
{RECONFIG}
  on Loss(k) match k {{
{loss_body}
  }}
}}
"""


class TestUnknownFailClosed(unittest.TestCase):
    def test_unknown_delay_ratio_constant(self):
        self.assertEqual(UNKNOWN_DELAY_RATIO, 1.35)

    def test_typed_loss_stamps_unknown_fail_closed(self):
        src = _src(
            """
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => require delay_ratio > 1.35 then cut(0.72) else hold
"""
        )
        res = check(parse(src, "unknown-fc.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.typed_loss)
        self.assertTrue(res.unknown_fail_closed)

    def test_unguarded_unknown_cut_fails_closed(self):
        src = _src(
            """
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => cut(0.72)
"""
        )
        res = check(parse(src, "unguarded-unknown.vela"))
        self.assertFalse(res.ok)
        joined = " ".join(res.errors)
        self.assertIn("Unknown cut", joined)
        self.assertIn("1.35", joined)

    def test_delay_ratio_le_guard_still_fails(self):
        # delay_ratio <= 1.35 is not a proof; cut must fail closed.
        src = _src(
            """
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => require delay_ratio <= 1.35 then cut(0.72) else hold
"""
        )
        res = check(parse(src, "le-guard.vela"))
        self.assertFalse(res.ok)
        joined = " ".join(res.errors)
        self.assertIn("Unknown cut", joined)

    def test_without_typed_loss_no_fail_closed_stamp(self):
        src = """
lang vela 0.1
controller Probe {
  posture review
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Loss(k) {
    cut(0.7)
  }
}
"""
        res = check(parse(src, "bare-loss-review.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.typed_loss)
        self.assertFalse(res.unknown_fail_closed)

    def test_reach_check_prints_fail_closed(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("loss=Mobility|Congestive|Unknown", out)
        self.assertIn("unknown=fail-closed", out)
        self.assertIn("delay_ratio<=1.35 refuses cut at check", out)
        # SoftReprobe not retuned
        self.assertIn("house cut 0.58", out)
        self.assertNotIn("softreprobe_cut=0.85", out)

    def test_horizon_check_prints_fail_closed(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "horizon.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("unknown=fail-closed", out)

    def test_docs_name_fail_closed(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        evaln = (ROOT / "docs" / "EVAL-NOTES.md").read_text(encoding="utf-8")
        self.assertIn("unknown=fail-closed", lang)
        self.assertIn("delay_ratio<=1.35", lang)
        self.assertIn("fail-closed, not advisory", lang)
        self.assertIn("unknown=fail-closed", equinox)
        self.assertIn("do not retune", equinox.lower())
        self.assertIn("unknown=fail-closed", evaln)
        self.assertIn("fail-closed, not advisory", evaln)


if __name__ == "__main__":
    unittest.main()
