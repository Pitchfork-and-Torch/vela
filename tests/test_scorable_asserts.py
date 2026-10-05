"""Contract asserts are a closed, scorable taxonomy (fail closed).

An assert the harness never reads used to check ok and ride an ACCEPT.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check
from vela.parser import parse
from vela.types import (
    DUAL_GATE_ASSERTS,
    SCORABLE_ASSERTS,
    SCORABLE_BASELINES,
    parse_mbps_literal,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

HOUSE_ASSERTS = """
  assert mean(goodput) >= baseline.goodput
  assert mean(p95) <= baseline.p95
  assert terrestrial.goodput >= 77 Mbps
"""


def _prog(asserts: str = HOUSE_ASSERTS, baseline: str = "BBRv3approx", scen: str = "") -> str:
    return f"""
lang vela 0.1
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
contract DualGate vs {baseline} {{
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
{scen}{asserts}}}
"""


def _errors(src: str) -> list[str]:
    return check(parse(src, "scorable.vela")).errors


class TestScorableTaxonomy(unittest.TestCase):
    def test_constants(self):
        self.assertIn("BBRv3approx", SCORABLE_BASELINES)
        self.assertEqual(SCORABLE_ASSERTS["mean(goodput)"], (">=", "baseline.goodput"))
        self.assertEqual(SCORABLE_ASSERTS["mean(p95)"], ("<=", "baseline.p95"))
        self.assertEqual(SCORABLE_ASSERTS["terrestrial.goodput"], (">=", "Mbps"))
        self.assertEqual(DUAL_GATE_ASSERTS, ("mean(goodput)", "mean(p95)"))

    def test_mbps_literal(self):
        self.assertEqual(parse_mbps_literal("77"), 77.0)
        self.assertEqual(parse_mbps_literal("77Mbps"), 77.0)
        self.assertEqual(parse_mbps_literal("77 Mbps"), 77.0)
        self.assertIsNone(parse_mbps_literal("40ms"))
        self.assertIsNone(parse_mbps_literal("90s"))
        self.assertIsNone(parse_mbps_literal("baseline.goodput"))

    def test_house_contract_checks_clean(self):
        res = check(parse(_prog(), "house.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(any("no mean(" in w for w in res.warnings), res.warnings)

    def test_every_shipped_example_is_scorable(self):
        for path in sorted(EX.glob("*.vela")):
            res = check(parse(path.read_text(encoding="utf-8"), path.name))
            self.assertFalse(
                any("not scorable" in e or "is reversed" in e for e in res.errors),
                (path.name, res.errors),
            )


class TestUnknownAssertFailsClosed(unittest.TestCase):
    def test_unknown_left_is_a_type_error(self):
        errs = _errors(_prog(HOUSE_ASSERTS + "  assert mean(loss_rate) <= 0.01\n"))
        self.assertTrue(any("mean(loss_rate) <= 0.01 is not scorable" in e for e in errs), errs)
        self.assertTrue(any("cannot ride an ACCEPT" in e for e in errs), errs)

    def test_error_names_the_scorable_forms(self):
        errs = _errors(_prog(HOUSE_ASSERTS + "  assert mean(handovers) <= 9\n"))
        joined = "\n".join(errs)
        self.assertIn("mean(goodput) >= baseline.goodput", joined)
        self.assertIn("mean(p95) <= baseline.p95", joined)
        self.assertIn("terrestrial.goodput >= <n> Mbps", joined)
        self.assertIn("mean(jain) >= <fraction>", joined)

    def test_reversed_p95_is_a_type_error(self):
        src = _prog(HOUSE_ASSERTS.replace("mean(p95) <= baseline.p95", "mean(p95) >= baseline.p95"))
        errs = _errors(src)
        self.assertTrue(any("mean(p95) >= baseline.p95 is reversed" in e for e in errs), errs)

    def test_reversed_goodput_is_a_type_error(self):
        src = _prog(
            HOUSE_ASSERTS.replace("mean(goodput) >= baseline.goodput", "mean(goodput) <= baseline.goodput")
        )
        errs = _errors(src)
        self.assertTrue(any("mean(goodput) <= baseline.goodput is reversed" in e for e in errs), errs)

    def test_reversed_terrestrial_is_a_type_error(self):
        src = _prog(HOUSE_ASSERTS.replace("terrestrial.goodput >= 77 Mbps", "terrestrial.goodput <= 77 Mbps"))
        errs = _errors(src)
        self.assertTrue(any("terrestrial.goodput <= 77Mbps is reversed" in e for e in errs), errs)

    def test_goodput_against_a_number_is_a_type_error(self):
        src = _prog(HOUSE_ASSERTS.replace("mean(goodput) >= baseline.goodput", "mean(goodput) >= 1"))
        errs = _errors(src)
        self.assertTrue(any("compares against 1" in e and "baseline.goodput" in e for e in errs), errs)

    def test_terrestrial_against_ms_is_a_type_error(self):
        src = _prog(HOUSE_ASSERTS.replace("terrestrial.goodput >= 77 Mbps", "terrestrial.goodput >= 40 ms"))
        errs = _errors(src)
        self.assertTrue(any("compares against 40ms" in e and "<n> Mbps" in e for e in errs), errs)

    def test_terrestrial_bare_number_is_ok(self):
        src = _prog(HOUSE_ASSERTS.replace("terrestrial.goodput >= 77 Mbps", "terrestrial.goodput >= 77"))
        self.assertEqual(_errors(src), [])

    def test_unknown_baseline_is_a_type_error(self):
        errs = _errors(_prog(baseline="CUBICish"))
        self.assertTrue(any("baseline CUBICish is not scorable" in e for e in errs), errs)
        self.assertTrue(any("BBRv3approx" in e for e in errs), errs)

    def test_jain_direction(self):
        scen = "  scenario leo_multi\n"
        ok = _errors(_prog(HOUSE_ASSERTS + "  assert mean(jain) >= 0.85\n", scen=scen))
        self.assertEqual(ok, [])
        bad = _errors(_prog(HOUSE_ASSERTS + "  assert mean(jain) <= 0.85\n", scen=scen))
        self.assertTrue(any("mean(jain) <= 0.85 is reversed" in e for e in bad), bad)


class TestMissingDualGateWarns(unittest.TestCase):
    def test_missing_p95_is_a_warning_not_an_error(self):
        src = _prog("  assert mean(goodput) >= baseline.goodput\n  assert terrestrial.goodput >= 77 Mbps\n")
        res = check(parse(src, "nop95.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("no mean(p95) assert" in w for w in res.warnings), res.warnings)
        self.assertFalse(any("no mean(goodput) assert" in w for w in res.warnings), res.warnings)

    def test_missing_both_warns_twice(self):
        src = _prog("  assert terrestrial.goodput >= 77 Mbps\n")
        res = check(parse(src, "nogate.vela"))
        self.assertTrue(res.ok, res.errors)
        hits = [w for w in res.warnings if "harness scores the dual gate anyway" in w]
        self.assertEqual(len(hits), 2, res.warnings)


if __name__ == "__main__":
    unittest.main()
