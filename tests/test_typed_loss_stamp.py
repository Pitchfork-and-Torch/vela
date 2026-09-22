"""TypedLoss observe law is a visible vela check stamp."""
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


class TestTypedLossStamp(unittest.TestCase):
    def test_unknown_delay_ratio_constant(self):
        self.assertEqual(UNKNOWN_DELAY_RATIO, 1.35)

    def test_typed_loss_stamps_delay_ratio(self):
        src = _src(
            """
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => require delay_ratio > 1.35 then cut(0.72) else hold
"""
        )
        res = check(parse(src, "typed-loss.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.typed_loss)
        self.assertEqual(res.unknown_needs_delay_ratio, UNKNOWN_DELAY_RATIO)
        self.assertEqual(res.unknown_needs_delay_ratio, 1.35)

    def test_without_typed_loss_no_delay_stamp(self):
        # bare Loss is illegal on observe; use review posture so check may pass
        # without the typed stamp path.
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
        self.assertIsNone(res.unknown_needs_delay_ratio)

    def test_reach_check_prints_preferred_stamps(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("typed_loss=Mobility|Congestive|Unknown", out)
        self.assertIn("unknown_needs_delay_ratio>1.35", out)
        # SoftReprobe not retuned
        self.assertIn("house cut 0.58", out)
        self.assertNotIn("softreprobe_cut=0.85", out)

    def test_horizon_check_prints_preferred_stamps(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "horizon.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("typed_loss=Mobility|Congestive|Unknown", out)
        self.assertIn("unknown_needs_delay_ratio>1.35", out)

    def test_docs_name_visible_stamps(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("typed_loss=Mobility|Congestive|Unknown", lang)
        self.assertIn("unknown_needs_delay_ratio>1.35", lang)
        self.assertIn("typed_loss=Mobility|Congestive|Unknown", equinox)
        self.assertIn("unknown_needs_delay_ratio>1.35", equinox)
        self.assertIn("do not retune", lang.lower())
        self.assertIn("do not retune", equinox.lower())
        self.assertIn("Mobility hold", lang)


if __name__ == "__main__":
    unittest.main()
