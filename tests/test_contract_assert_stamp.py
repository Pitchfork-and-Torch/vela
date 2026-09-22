"""contract=assert|report honesty stamp on check/eval.

When a contract block is present, stamp assert|report with CI/power
required and refuse silent claim wins (no assert is a type error).
Does not redo #58 eval-summary, #70 power-low, #66 dual-gate.
"""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.eval_harness import _summarize, honesty_text
from vela.ir import VelaConfig, program_to_config
from vela.parser import parse
from vela.types import (
    CONTRACT_ASSERT_NOTE,
    CONTRACT_ASSERT_STAMP,
    HOUSE_ENDPOINT_CUT,
    contract_assert_cli_line,
    contract_assert_modes,
    contract_silent_claim_error,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
HOUSE = [13, 7, 42, 99, 123]


CTRL = """
lang vela 0.1
use std.epoch
use std.mech
use std.eval
controller Reach {
  posture observe
  compose Detect + SoftReprobe + DualGateGuard
  signals:
    epoch: Epoch
  on Reconfig(e) match e {
    RttHop => { enter Reprobe }
    Flicker => { enter Reprobe }
  }
  on Loss(k) match k {
    Mobility => {}
    Congestive => {}
    Unknown => { if delay_ratio > 1.35 { cut(0.58) } }
  }
}
"""


def _rows(scenario: str, cca: str, gp: float, p95: float, seeds=None):
    return [
        {
            "scenario": scenario,
            "seed": seed,
            "cca": cca,
            "goodput_mbps": gp,
            "p95_rtt_ms": p95,
        }
        for seed in (seeds if seeds is not None else HOUSE)
    ]


class TestHelpers(unittest.TestCase):
    def test_softreprobe_cut_held(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_modes(self):
        self.assertEqual(contract_assert_modes(3, 2), "assert|report")
        self.assertEqual(contract_assert_modes(1, 0), "assert")
        self.assertEqual(contract_assert_modes(0, 1), "report")
        self.assertEqual(contract_assert_modes(0, 0), "empty")

    def test_cli_line_names_refuse(self):
        line = contract_assert_cli_line(
            "assert|report", name="DualGate", baseline="BBRv3approx"
        )
        self.assertTrue(line.startswith(CONTRACT_ASSERT_STAMP))
        self.assertIn("DualGate vs BBRv3approx", line)
        self.assertIn(CONTRACT_ASSERT_NOTE, line)
        self.assertIn("refuse silent claim wins", line)
        self.assertIn("ci+power required", line)

    def test_silent_claim_error_text(self):
        msg = contract_silent_claim_error("DualGate")
        self.assertIn("no assert", msg)
        self.assertIn("refuse silent claim wins", msg)


class TestReachCheckStamp(unittest.TestCase):
    def test_reach_stamps_assert_report(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.contract_assert, "assert|report")

    def test_reach_check_cli_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(CONTRACT_ASSERT_STAMP, out)
        self.assertIn(CONTRACT_ASSERT_NOTE, out)
        self.assertIn("DualGate vs BBRv3approx", out)
        self.assertIn("0.58", out)

    def test_cfg_carries_stamp(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        cfg = program_to_config(parse(src, "reach.vela"))
        self.assertEqual(cfg.contract_assert, "assert|report")
        self.assertTrue(cfg.reports)


class TestRefuseSilentClaim(unittest.TestCase):
    def test_no_assert_is_type_error(self):
        src = (
            CTRL
            + """
contract DualGate vs BBRv3approx {
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  report ci(0.95)
}
"""
        )
        res = check(parse(src, "no-assert.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("refuse silent claim wins" in e for e in res.errors),
            res.errors,
        )
        self.assertEqual(res.contract_assert, "report")

    def test_assert_only_stamps_assert(self):
        src = (
            CTRL
            + """
contract DualGate vs BBRv3approx {
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  assert terrestrial.goodput >= 77 Mbps
}
"""
        )
        res = check(parse(src, "assert-only.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.contract_assert, "assert")
        line = contract_assert_cli_line(res.contract_assert, name="DualGate", baseline="BBRv3approx")
        self.assertIn("contract=assert  ", line)
        self.assertNotIn("assert|report", line)


class TestEvalSummaryStamp(unittest.TestCase):
    def test_summary_carries_contract_assert(self):
        cfg = VelaConfig(
            name="Reach",
            seeds=list(HOUSE),
            duration_s=90.0,
            contract_assert="assert|report",
            reports=["ci(0.95)"],
        )
        rows = (
            _rows("leo_fast_ho", "Reach", 80.0, 120.0)
            + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0)
            + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0)
            + _rows("terrestrial", "Reach", 78.0, 40.0)
        )
        summary = _summarize(rows, cfg, duration_s=90.0)
        self.assertEqual(summary["contract_assert"], "assert|report")
        self.assertIn("contract=assert|report", summary["honesty"])
        self.assertIn(CONTRACT_ASSERT_NOTE, summary["honesty"])
        self.assertIn("refuse silent claim wins", honesty_text("house", "assert|report"))


class TestDocsCiteStamp(unittest.TestCase):
    def test_language_names_stamp(self):
        text = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("contract=assert|report", text)
        self.assertIn("refuse silent claim wins", text)


if __name__ == "__main__":
    unittest.main()
