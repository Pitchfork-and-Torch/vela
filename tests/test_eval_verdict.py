"""Fixture tests for eval harness top-level ACCEPT / FAIL / INCOMPLETE."""
from __future__ import annotations

import unittest

from vela.eval_harness import _summarize
from vela.ir import VelaConfig

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


if __name__ == "__main__":
    unittest.main()
