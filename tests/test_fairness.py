"""Optional leo_multi Jain assert. Missing scenario is INCOMPLETE, not a README."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check, fairness_needs_multi_error
from vela.eval_harness import _summarize, jain_index
from vela.ir import VelaConfig, program_to_config
from vela.parser import parse
from vela.types import FAIRNESS_SCENARIO

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
CCA = "Reach"
HOUSE = [13, 7, 42, 99, 123]


def _rows(scenario: str, cca: str, gp: float, p95: float, *, jain: float | None = None):
    out = []
    for seed in HOUSE:
        rec = {
            "scenario": scenario,
            "seed": seed,
            "cca": cca,
            "goodput_mbps": gp,
            "p95_rtt_ms": p95,
        }
        if jain is not None:
            rec["jain_fairness"] = jain
        out.append(rec)
    return out


def _passing_core():
    return (
        _rows("leo_fast_ho", CCA, 80.0, 120.0)
        + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0)
        + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0)
        + _rows("terrestrial", CCA, 78.0, 40.0)
    )


class TestJainIndex(unittest.TestCase):
    def test_equal_flows_are_one(self):
        self.assertAlmostEqual(jain_index([10.0, 10.0, 10.0]), 1.0)

    def test_empty_is_nan(self):
        import math

        self.assertTrue(math.isnan(jain_index([])))


class TestFairnessContract(unittest.TestCase):
    def test_fair_example_parses_and_checks(self):
        src = (EX / "fair.vela").read_text(encoding="utf-8")
        prog = parse(src, "fair.vela")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.fairness, FAIRNESS_SCENARIO)
        self.assertEqual(res.jain_min, 0.85)
        self.assertTrue(res.observe_only)
        self.assertTrue(res.passthrough)
        self.assertTrue(res.no_oracle)
        self.assertIn(FAIRNESS_SCENARIO, prog.contracts[0].scenarios)
        self.assertIn("leo_fast_ho", prog.contracts[0].scenarios)
        cfg = program_to_config(prog)
        self.assertEqual(cfg.jain_min, 0.85)
        self.assertIn(FAIRNESS_SCENARIO, cfg.scenarios)

    def test_jain_without_leo_multi_is_error(self):
        src = """
lang vela 0.4
controller Probe {
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
  on Reconfig(e) match e {
    RttHop => enter Reprobe(cut: 0.58)
    Flicker => enter Reprobe(cut: 0.58)
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
contract DualGate vs BBRv3approx {
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  assert mean(jain) >= 0.85
  assert terrestrial.goodput >= 77 Mbps
}
"""
        res = check(parse(src, "jain-only.vela"))
        self.assertFalse(res.ok)
        self.assertIn(fairness_needs_multi_error("DualGate"), res.errors)

    def test_leo_multi_without_jain_warns(self):
        src = """
lang vela 0.4
controller Probe {
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
  on Reconfig(e) match e {
    RttHop => enter Reprobe(cut: 0.58)
    Flicker => enter Reprobe(cut: 0.58)
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
contract DualGate vs BBRv3approx {
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  scenario leo_multi
  assert terrestrial.goodput >= 77 Mbps
}
"""
        res = check(parse(src, "multi-nojain.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("without a jain assert" in w for w in res.warnings))

    def test_multiple_scenario_lines_append(self):
        src = """
lang vela 0.4
controller Probe {
  compose Detect
}
contract DualGate vs BBRv3approx {
  seeds = [13]
  scenario leo_fast_ho duration 90s
  scenario leo_multi
  scenario terrestrial
}
"""
        prog = parse(src, "multi-scen.vela")
        self.assertEqual(
            prog.contracts[0].scenarios,
            ["leo_fast_ho", "leo_multi", "terrestrial"],
        )

    def test_harness_accept_when_jain_clears(self):
        cfg = VelaConfig(name=CCA, seeds=list(HOUSE), jain_min=0.85)
        rows = _passing_core() + _rows("leo_multi", CCA, 40.0, 140.0, jain=0.92)
        summary = _summarize(rows, cfg)
        self.assertEqual(summary["verdict"], "ACCEPT")
        fair = next(a for a in summary["asserts"] if a["assert"] == "fairness_jain")
        self.assertTrue(fair["ok"])
        self.assertEqual(fair["jain_mean"], 0.92)

    def test_harness_fail_when_jain_below_floor(self):
        cfg = VelaConfig(name=CCA, seeds=list(HOUSE), jain_min=0.85)
        rows = _passing_core() + _rows("leo_multi", CCA, 40.0, 140.0, jain=0.50)
        summary = _summarize(rows, cfg)
        self.assertEqual(summary["verdict"], "FAIL")
        fair = next(a for a in summary["asserts"] if a["assert"] == "fairness_jain")
        self.assertFalse(fair["ok"])

    def test_harness_incomplete_when_jain_asked_without_rows(self):
        cfg = VelaConfig(name=CCA, seeds=list(HOUSE), jain_min=0.85)
        summary = _summarize(_passing_core(), cfg)
        self.assertEqual(summary["verdict"], "INCOMPLETE")
        fair = next(a for a in summary["asserts"] if a["assert"] == "fairness_jain")
        self.assertEqual(fair.get("note"), "INCOMPLETE")
        self.assertNotEqual(summary["verdict"], "ACCEPT")


if __name__ == "__main__":
    unittest.main()
