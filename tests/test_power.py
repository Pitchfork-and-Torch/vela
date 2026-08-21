"""power=low is n<8 at check and eval. Five-seed ACCEPT stays legal."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check, power_low_warning
from vela.eval_harness import _summarize
from vela.ir import VelaConfig
from vela.parser import parse
from vela.types import POWER_OK_MIN_SEEDS, eval_power

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
CCA = "Reach"
HOUSE = [13, 7, 42, 99, 123]


def _cfg(seeds: list[int] | None = None) -> VelaConfig:
    return VelaConfig(name=CCA, seeds=list(seeds if seeds is not None else HOUSE))


def _rows(
    scenario: str, cca: str, gp: float, p95: float, seeds: list[int] | None = None
) -> list[dict]:
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


def _passing_leo_fast_ho(seeds: list[int] | None = None) -> list[dict]:
    return (
        _rows("leo_fast_ho", CCA, 80.0, 120.0, seeds)
        + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0, seeds)
        + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0, seeds)
    )


def _contract_src(seeds: list[int]) -> str:
    listed = ", ".join(str(s) for s in seeds)
    return f"""
lang vela 0.1
controller Probe {{
  compose Detect + SoftReprobe + IntervalBw
  signals:
    epoch: Epoch
  on Reconfig(e) match e {{
    RttHop => enter Reprobe(cut: 0.58)
    Flicker => enter Reprobe(cut: 0.58)
  }}
  on Loss(k) match k {{
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }}
}}
contract DualGate vs BBRv3approx {{
  seeds = [{listed}]
  scenario leo_fast_ho duration 90s
  assert mean(goodput) >= baseline.goodput
  assert terrestrial.goodput >= 77 Mbps
}}
"""


class TestPowerLowAlign(unittest.TestCase):
    def test_shared_floor_is_eight(self):
        self.assertEqual(POWER_OK_MIN_SEEDS, 8)
        self.assertEqual(eval_power(7), "low")
        self.assertEqual(eval_power(5), "low")
        self.assertEqual(eval_power(8), "ok")
        self.assertEqual(eval_power(9), "ok")

    def test_house_five_seeds_warn_and_check(self):
        src = _contract_src(HOUSE)
        res = check(parse(src, "house5.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.power, "low")
        self.assertIn(power_low_warning("DualGate", 5), res.warnings)

    def test_eight_seeds_is_power_ok(self):
        seeds = [13, 7, 42, 99, 123, 17, 19, 23]
        res = check(parse(_contract_src(seeds), "n8.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.power, "ok")
        self.assertFalse(any("power=low" in w for w in res.warnings))

    def test_reach_house_contract_is_power_low(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.power, "low")
        self.assertTrue(any("power=low" in w for w in res.warnings))

    def test_harness_five_seeds_accept_is_still_low(self):
        rows = _passing_leo_fast_ho() + _rows("terrestrial", CCA, 78.0, 40.0)
        summary = _summarize(rows, _cfg())
        self.assertEqual(summary["verdict"], "ACCEPT")
        self.assertEqual(summary["power"], "low")
        self.assertIn(f"n<{POWER_OK_MIN_SEEDS}", summary["honesty"])

    def test_harness_eight_seeds_is_ok(self):
        seeds = [13, 7, 42, 99, 123, 17, 19, 23]
        cfg = _cfg()
        cfg.seeds = list(seeds)
        rows = _passing_leo_fast_ho(seeds) + _rows("terrestrial", CCA, 78.0, 40.0, seeds)
        summary = _summarize(rows, cfg)
        self.assertEqual(summary["verdict"], "ACCEPT")
        self.assertEqual(summary["power"], "ok")

    def test_warning_text_names_floor(self):
        msg = power_low_warning("DualGate", 5)
        self.assertIn("n<8", msg)
        self.assertIn("DualGate", msg)
        self.assertIn("5 seeds", msg)


if __name__ == "__main__":
    unittest.main()
