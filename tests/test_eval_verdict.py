"""Fixture tests for eval harness top-level ACCEPT / FAIL / INCOMPLETE."""
from __future__ import annotations

import json
import unittest

from vela.eval_harness import _fmt_mean_std, _summarize
from vela.ir import VelaConfig, parse_report_ci

SEEDS = [13, 7, 42, 99, 123]
CCA = "Reach"


def _cfg() -> VelaConfig:
    return VelaConfig(name=CCA, seeds=list(SEEDS))


def _rows(scenario: str, cca: str, gp: float, p95: float, seeds: list[int] | None = None) -> list[dict]:
    return [
        {
            "scenario": scenario,
            "seed": seed,
            "cca": cca,
            "goodput_mbps": gp,
            "p95_rtt_ms": p95,
        }
        for seed in (seeds if seeds is not None else SEEDS)
    ]


def _passing_leo_fast_ho(seeds: list[int] | None = None) -> list[dict]:
    # Fixture-only means. Not a dual-gate claim.
    return (
        _rows("leo_fast_ho", CCA, 80.0, 120.0, seeds)
        + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0, seeds)
        + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0, seeds)
    )


def _assert_named(summary: dict, name: str) -> dict:
    for item in summary["asserts"]:
        if item.get("assert") == name:
            return item
    raise AssertionError(f"missing assert {name}: {summary['asserts']}")


class TestEvalVerdict(unittest.TestCase):
    def test_accept_when_required_asserts_present_and_ok(self):
        rows = _passing_leo_fast_ho() + _rows("terrestrial", CCA, 78.0, 40.0)
        summary = _summarize(rows, _cfg())
        self.assertEqual(summary["verdict"], "ACCEPT")
        self.assertEqual(summary["power"], "low")
        self.assertTrue(_assert_named(summary, "dual_gate_vs_BBR")["ok"])
        self.assertTrue(_assert_named(summary, "pareto_vs_LeoAware")["ok"])
        self.assertTrue(_assert_named(summary, "terrestrial_floor")["ok"])
        self.assertNotEqual(summary["verdict"], "INCOMPLETE")

    def test_fail_when_terrestrial_present_below_floor(self):
        rows = _passing_leo_fast_ho() + _rows("terrestrial", CCA, 60.0, 40.0)
        summary = _summarize(rows, _cfg())
        self.assertEqual(summary["verdict"], "FAIL")
        terr = _assert_named(summary, "terrestrial_floor")
        self.assertFalse(terr["ok"])
        self.assertNotIn("note", terr)
        self.assertTrue(_assert_named(summary, "dual_gate_vs_BBR")["ok"])

    def test_incomplete_when_terrestrial_row_missing(self):
        summary = _summarize(_passing_leo_fast_ho(), _cfg())
        self.assertEqual(summary["verdict"], "INCOMPLETE")
        terr = _assert_named(summary, "terrestrial_floor")
        self.assertFalse(terr["ok"])
        self.assertEqual(terr.get("note"), "INCOMPLETE")
        self.assertNotEqual(summary["verdict"], "ACCEPT")
        self.assertNotEqual(summary["verdict"], "FAIL")

    def test_incomplete_not_fail_when_dual_gate_misses_without_terrestrial(self):
        rows = (
            _rows("leo_fast_ho", CCA, 60.0, 150.0)
            + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0)
            + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0)
        )
        summary = _summarize(rows, _cfg())
        self.assertEqual(summary["verdict"], "INCOMPLETE")
        self.assertFalse(_assert_named(summary, "dual_gate_vs_BBR")["ok"])
        self.assertEqual(_assert_named(summary, "terrestrial_floor").get("note"), "INCOMPLETE")

    def test_fail_when_dual_gate_misses_and_terrestrial_present(self):
        rows = (
            _rows("leo_fast_ho", CCA, 60.0, 150.0)
            + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0)
            + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0)
            + _rows("terrestrial", CCA, 78.0, 40.0)
        )
        summary = _summarize(rows, _cfg())
        self.assertEqual(summary["verdict"], "FAIL")
        self.assertFalse(_assert_named(summary, "dual_gate_vs_BBR")["ok"])
        self.assertTrue(_assert_named(summary, "terrestrial_floor")["ok"])

    def test_incomplete_when_n_seeds_below_contract_minimum(self):
        short = [13, 7]
        rows = _passing_leo_fast_ho(short) + _rows("terrestrial", CCA, 78.0, 40.0, short)
        summary = _summarize(rows, _cfg())
        self.assertEqual(summary["verdict"], "INCOMPLETE")
        self.assertEqual(summary["power"], "low")
        seed_count = _assert_named(summary, "seed_count")
        self.assertEqual(seed_count.get("note"), "INCOMPLETE")
        self.assertEqual(seed_count["n"], 2)
        self.assertEqual(seed_count["contract_min"], 5)

    def test_default_config_omits_ci_object(self):
        rows = _passing_leo_fast_ho() + _rows("terrestrial", CCA, 78.0, 40.0)
        summary = _summarize(rows, _cfg())
        self.assertNotIn("ci", summary)

    def test_report_ci_is_mean_plus_minus_std(self):
        cfg = _cfg()
        cfg.reports = ["ci(0.95)", "ablation"]
        rows = (
            _rows("leo_fast_ho", CCA, 80.0, 120.0)
            + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0)
            + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0)
            + _rows("terrestrial", CCA, 78.0, 40.0)
        )
        summary = _summarize(rows, cfg)
        ci = summary["ci"]
        self.assertEqual(ci["level"], 0.95)
        self.assertEqual(ci["method"], "mean+/-std")
        self.assertIn("Not a bootstrap", ci["note"])
        reach = next(
            r
            for r in ci["rows"]
            if r["scenario"] == "leo_fast_ho" and r["cca"] == CCA
        )
        self.assertEqual(reach["n"], 5)
        self.assertEqual(reach["goodput"], _fmt_mean_std(80.0, 0.0))
        self.assertEqual(reach["p95"], _fmt_mean_std(120.0, 0.0))
        self.assertEqual(reach["goodput"], "80.000 +/- 0.000")
        self.assertNotIn("p<", json.dumps(ci))
        self.assertNotIn("bootstrap interval", ci["note"].lower())

    def test_report_ci_uses_sample_std(self):
        cfg = _cfg()
        cfg.reports = ["ci"]
        cfg.seeds = [13, 7]
        rows = (
            [
                {
                    "scenario": "leo_fast_ho",
                    "seed": 13,
                    "cca": CCA,
                    "goodput_mbps": 80.0,
                    "p95_rtt_ms": 100.0,
                },
                {
                    "scenario": "leo_fast_ho",
                    "seed": 7,
                    "cca": CCA,
                    "goodput_mbps": 84.0,
                    "p95_rtt_ms": 110.0,
                },
            ]
            + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0, [13, 7])
            + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0, [13, 7])
            + _rows("terrestrial", CCA, 78.0, 40.0, [13, 7])
        )
        summary = _summarize(rows, cfg)
        reach = next(
            r
            for r in summary["ci"]["rows"]
            if r["scenario"] == "leo_fast_ho" and r["cca"] == CCA
        )
        self.assertAlmostEqual(reach["goodput_mean"], 82.0)
        self.assertAlmostEqual(reach["goodput_std"], (8.0 ** 0.5), places=3)
        self.assertEqual(reach["goodput"], _fmt_mean_std(82.0, 8.0 ** 0.5))
        self.assertEqual(summary["ci"]["level"], 0.95)

    def test_parse_report_ci_rejects_out_of_range(self):
        level, errs = parse_report_ci(["ci(1.5)"])
        self.assertIsNone(level)
        self.assertTrue(any("must be in (0, 1)" in e for e in errs))
        level, errs = parse_report_ci(["ci(high)"])
        self.assertIsNone(level)
        self.assertTrue(any("must be a number" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
