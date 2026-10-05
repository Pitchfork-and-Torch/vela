"""The harness scores the terrestrial floor the contract names.

`assert terrestrial.goodput >= 90 Mbps` used to be scored against a
literal 77.0 / 40.5 in the harness. The floor now binds from the text,
the receipt commits it, and a floor looser than the house rail is a
type error on observe (review warns).
"""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.eval_harness import _summarize
from vela.ir import VelaConfig, program_to_config
from vela.parser import parse
from vela.receipt import build_receipt
from vela.types import (
    HOUSE_TERRESTRIAL_GP_MBPS,
    HOUSE_TERRESTRIAL_P95_MS,
    contract_terrestrial_floor,
    parse_ms_literal,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
SEEDS = [13, 7, 42, 99, 123]
CCA = "Probe"


def _prog(terr: str = "  assert terrestrial.goodput >= 77 Mbps\n", posture: str = "observe") -> str:
    return f"""
lang vela 0.1
use std.eval
controller {CCA} {{
  posture {posture}
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
contract DualGate vs BBRv3approx {{
  seeds = [13, 7, 42, 99, 123]
  scenario leo_fast_ho duration 90s
  assert mean(goodput) >= baseline.goodput
  assert mean(p95) <= baseline.p95
{terr}}}
"""


def _rows(scenario: str, cca: str, gp: float, p95: float) -> list[dict]:
    return [
        {"scenario": scenario, "seed": s, "cca": cca, "goodput_mbps": gp, "p95_rtt_ms": p95}
        for s in SEEDS
    ]


def _passing_leo() -> list[dict]:
    return (
        _rows("leo_fast_ho", CCA, 80.0, 120.0)
        + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0)
        + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0)
    )


def _terr_assert(summary: dict) -> dict:
    for a in summary["asserts"]:
        if a.get("assert") == "terrestrial_floor":
            return a
    raise AssertionError(summary["asserts"])


class TestFloorParse(unittest.TestCase):
    def test_house_constants(self):
        self.assertEqual(HOUSE_TERRESTRIAL_GP_MBPS, 77.0)
        self.assertEqual(HOUSE_TERRESTRIAL_P95_MS, 40.5)

    def test_ms_literal(self):
        self.assertEqual(parse_ms_literal("40.5"), 40.5)
        self.assertEqual(parse_ms_literal("40.5ms"), 40.5)
        self.assertEqual(parse_ms_literal("40 ms"), 40.0)
        self.assertIsNone(parse_ms_literal("77Mbps"))
        self.assertIsNone(parse_ms_literal("90s"))

    def test_contract_floor_from_text(self):
        con = parse(_prog("  assert terrestrial.goodput >= 90 Mbps\n  assert terrestrial.p95 <= 38 ms\n"), "f.vela").contracts[0]
        self.assertEqual(contract_terrestrial_floor(con.asserts), (90.0, 38.0))

    def test_contract_floor_absent_is_none(self):
        con = parse(_prog(""), "f.vela").contracts[0]
        self.assertEqual(contract_terrestrial_floor(con.asserts), (None, None))


class TestCheckBindsFloor(unittest.TestCase):
    def test_house_floor_on_reach(self):
        res = check(parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.terrestrial_floor_mbps, 77.0)
        self.assertEqual(res.terrestrial_p95_ms, 40.5)

    def test_stricter_floor_binds(self):
        res = check(parse(_prog("  assert terrestrial.goodput >= 90 Mbps\n  assert terrestrial.p95 <= 38 ms\n"), "s.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.terrestrial_floor_mbps, 90.0)
        self.assertEqual(res.terrestrial_p95_ms, 38.0)

    def test_missing_floor_falls_back_to_house(self):
        res = check(parse(_prog(""), "m.vela"))
        self.assertEqual(res.terrestrial_floor_mbps, 77.0)
        self.assertEqual(res.terrestrial_p95_ms, 40.5)
        self.assertTrue(any("missing terrestrial assert" in w for w in res.warnings), res.warnings)

    def test_loose_goodput_floor_is_a_type_error_on_observe(self):
        res = check(parse(_prog("  assert terrestrial.goodput >= 70 Mbps\n"), "loose.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("terrestrial.goodput floor 70 is looser than the house rail 77" in e for e in res.errors),
            res.errors,
        )

    def test_loose_p95_cap_is_a_type_error_on_observe(self):
        res = check(parse(_prog("  assert terrestrial.goodput >= 77 Mbps\n  assert terrestrial.p95 <= 60 ms\n"), "loose95.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("terrestrial.p95 floor 60 is looser than the house rail 40.5" in e for e in res.errors),
            res.errors,
        )

    def test_loose_floor_is_a_warning_on_review(self):
        res = check(parse(_prog("  assert terrestrial.goodput >= 70 Mbps\n", posture="review"), "rev.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("looser than the house rail 77" in w and "review" in w for w in res.warnings), res.warnings)
        self.assertEqual(res.terrestrial_floor_mbps, 70.0)

    def test_p95_against_mbps_is_a_type_error(self):
        res = check(parse(_prog("  assert terrestrial.goodput >= 77 Mbps\n  assert terrestrial.p95 <= 40 Mbps\n"), "unit.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("terrestrial.p95 compares against 40Mbps" in e for e in res.errors), res.errors)


class TestCompileBindsFloor(unittest.TestCase):
    def test_default_config_is_house(self):
        cfg = VelaConfig()
        self.assertEqual(cfg.terrestrial_floor_mbps, 77.0)
        self.assertEqual(cfg.terrestrial_p95_ms, 40.5)

    def test_program_to_config_reads_text(self):
        cfg = program_to_config(parse(_prog("  assert terrestrial.goodput >= 90 Mbps\n  assert terrestrial.p95 <= 38 ms\n"), "c.vela"))
        self.assertEqual(cfg.terrestrial_floor_mbps, 90.0)
        self.assertEqual(cfg.terrestrial_p95_ms, 38.0)

    def test_reach_config_is_house(self):
        cfg = program_to_config(parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela"))
        self.assertEqual(cfg.terrestrial_floor_mbps, 77.0)
        self.assertEqual(cfg.terrestrial_p95_ms, 40.5)


class TestHarnessScoresContractFloor(unittest.TestCase):
    def test_house_floor_accepts_78(self):
        cfg = VelaConfig(name=CCA, seeds=list(SEEDS))
        summary = _summarize(_passing_leo() + _rows("terrestrial", CCA, 78.0, 40.0), cfg)
        self.assertEqual(summary["verdict"], "ACCEPT")
        terr = _terr_assert(summary)
        self.assertTrue(terr["ok"])
        self.assertEqual(terr["floor_mbps"], 77.0)
        self.assertEqual(terr["p95_cap_ms"], 40.5)

    def test_contract_floor_90_fails_78(self):
        cfg = VelaConfig(name=CCA, seeds=list(SEEDS), terrestrial_floor_mbps=90.0)
        summary = _summarize(_passing_leo() + _rows("terrestrial", CCA, 78.0, 40.0), cfg)
        self.assertEqual(summary["verdict"], "FAIL")
        terr = _terr_assert(summary)
        self.assertFalse(terr["ok"])
        self.assertNotIn("note", terr)
        self.assertEqual(terr["floor_mbps"], 90.0)

    def test_contract_p95_cap_38_fails_40(self):
        cfg = VelaConfig(name=CCA, seeds=list(SEEDS), terrestrial_p95_ms=38.0)
        summary = _summarize(_passing_leo() + _rows("terrestrial", CCA, 78.0, 40.0), cfg)
        self.assertEqual(summary["verdict"], "FAIL")
        self.assertEqual(_terr_assert(summary)["p95_cap_ms"], 38.0)

    def test_missing_terrestrial_still_incomplete_and_names_floor(self):
        cfg = VelaConfig(name=CCA, seeds=list(SEEDS), terrestrial_floor_mbps=90.0)
        summary = _summarize(_passing_leo(), cfg)
        self.assertEqual(summary["verdict"], "INCOMPLETE")
        terr = _terr_assert(summary)
        self.assertEqual(terr.get("note"), "INCOMPLETE")
        self.assertEqual(terr["floor_mbps"], 90.0)

    def test_receipt_commits_the_floor(self):
        cfg = VelaConfig(name=CCA, seeds=list(SEEDS))
        summary = _summarize(_passing_leo() + _rows("terrestrial", CCA, 78.0, 40.0), cfg)
        summary["rows"] = []
        base = {"name": CCA, "seeds": SEEDS, "scenarios": ["leo_fast_ho", "terrestrial"], "duration_s": 90.0}
        a = build_receipt(source="x", source_name="x.vela", compose=["Detect"],
                          config={**base, "terrestrial_floor_mbps": 77.0}, summary=summary)
        b = build_receipt(source="x", source_name="x.vela", compose=["Detect"],
                          config={**base, "terrestrial_floor_mbps": 70.0}, summary=summary)
        self.assertNotEqual(a["config_digest"], b["config_digest"])
        self.assertNotEqual(a["receipt_digest"], b["receipt_digest"])


class TestCheckLine(unittest.TestCase):
    def _check(self, src: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.vela"
            p.write_text(src, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vela_main(["check", str(p)])
        return rc, buf.getvalue()

    def test_reach_prints_house_rail(self):
        rc, out = self._check((EX / "reach.vela").read_text(encoding="utf-8"))
        self.assertEqual(rc, 0, out)
        self.assertIn("terrestrial>=77Mbps p95<=40.5ms  (house rail)", out)

    def test_contract_floor_prints_that_it_is_scored(self):
        rc, out = self._check(_prog("  assert terrestrial.goodput >= 90 Mbps\n"))
        self.assertEqual(rc, 0, out)
        self.assertIn("terrestrial>=90Mbps p95<=40.5ms  (contract floor; harness scores it)", out)


if __name__ == "__main__":
    unittest.main()
