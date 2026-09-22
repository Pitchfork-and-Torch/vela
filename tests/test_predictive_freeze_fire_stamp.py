"""PredictiveFreeze fire-condition honesty: needs 3 HO-scale gaps."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    check,
    controller_stamps_predictive_freeze,
    predictive_freeze_fire_line,
)
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import (
    PREDICTIVE_FREEZE_FIRE_STAMP,
    PREDICTIVE_FREEZE_MIN_HO_GAPS,
    PREDICTIVE_FREEZE_P_HO,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(compose: str, body: str = "") -> str:
    return f"""
lang vela 0.1
controller Probe {{
  posture observe
  compose {compose}
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


class TestPredictiveFreezeFireStamp(unittest.TestCase):
    def test_constants_match_language_eval(self):
        self.assertEqual(PREDICTIVE_FREEZE_MIN_HO_GAPS, 3)
        self.assertEqual(PREDICTIVE_FREEZE_P_HO, 0.55)
        self.assertEqual(PREDICTIVE_FREEZE_FIRE_STAMP, "needs_3_ho_gaps")
        line = predictive_freeze_fire_line()
        self.assertIn("predictive_freeze=needs_3_ho_gaps", line)
        self.assertIn("3 HO-scale gaps", line)

    def test_compose_with_predictive_freeze_stamps(self):
        src = _src(
            "Detect + SoftReprobe + PredictiveFreeze",
            "  when p_ho > 0.55 {\n    freeze min_rtt, bw for 1.4 * rtt\n  }\n",
        )
        prog = parse(src, "with-pf.vela")
        self.assertTrue(controller_stamps_predictive_freeze(prog.controllers[0]))
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.predictive_freeze, PREDICTIVE_FREEZE_FIRE_STAMP)

    def test_without_predictive_freeze_no_stamp(self):
        src = _src("Detect + SoftReprobe + Calendar + IntervalBw")
        prog = parse(src, "no-pf.vela")
        self.assertFalse(controller_stamps_predictive_freeze(prog.controllers[0]))
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.predictive_freeze, "")

    def test_horizon_check_prints_fire_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "horizon.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("predictive_freeze=needs_3_ho_gaps", out)
        self.assertIn("3 HO-scale gaps", out)

    def test_reach_check_no_predictive_freeze_stamp(self):
        # Reach uses Calendar, not PredictiveFreeze; fire stamp is PF-only.
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("predictive_freeze=needs_3_ho_gaps", out)

    def test_docs_name_fire_condition(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        eval_notes = (ROOT / "docs" / "EVAL-NOTES.md").read_text(encoding="utf-8")
        self.assertIn("three real HO-scale gaps", lang)
        self.assertIn("p_ho > 0.55", lang)
        self.assertIn("needs 3 HO-scale gaps", eval_notes)
        self.assertIn("predictive_freeze=needs_3_ho_gaps", lang)

    def test_kernel_pred_uses_min_gaps_constant(self):
        from vela import kernel as k

        self.assertEqual(k.PREDICTIVE_FREEZE_MIN_HO_GAPS, 3)
        src = Path(k.__file__).read_text(encoding="utf-8")
        self.assertIn("PREDICTIVE_FREEZE_MIN_HO_GAPS", src)
        self.assertNotIn("len(self._ho_gaps) < 2", src)


if __name__ == "__main__":
    unittest.main()
