"""power=low CLI stamp on check / eval / receipt. Not a journal claim."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main
from vela.eval_harness import _summarize
from vela.ir import VelaConfig
from vela.parser import parse
from vela.receipt import build_receipt, write_receipt
from vela.types import HOUSE_ENDPOINT_CUT, POWER_OK_MIN_SEEDS, eval_power, power_cli_line

CCA = "Reach"
HOUSE = [13, 7, 42, 99, 123]


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


def _rows(scenario: str, cca: str, gp: float, p95: float, seeds: list[int]) -> list[dict]:
    return [
        {
            "scenario": scenario,
            "seed": seed,
            "cca": cca,
            "goodput_mbps": gp,
            "p95_rtt_ms": p95,
        }
        for seed in seeds
    ]


def _passing(seeds: list[int]) -> list[dict]:
    return (
        _rows("leo_fast_ho", CCA, 80.0, 120.0, seeds)
        + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0, seeds)
        + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0, seeds)
        + _rows("terrestrial", CCA, 78.0, 40.0, seeds)
    )


class TestPowerCliLine(unittest.TestCase):
    def test_low_names_floor_and_not_journal(self):
        line = power_cli_line(5)
        self.assertEqual(line, "power=low  n=5  n<8  not journal")
        self.assertIn(f"n<{POWER_OK_MIN_SEEDS}", line)
        self.assertNotIn("p<", line.lower())
        self.assertNotIn("journal result", line)

    def test_ok_at_eight(self):
        line = power_cli_line(8)
        self.assertEqual(line, "power=ok  n=8  n>=8")
        self.assertNotIn("not journal", line)

    def test_softreprobe_untouched(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)
        self.assertEqual(eval_power(5), "low")
        self.assertEqual(eval_power(8), "ok")


class TestCheckStamp(unittest.TestCase):
    def test_check_cli_prints_not_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "house5.vela"
            path.write_text(_contract_src(HOUSE), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["check", str(path)])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("power=low  n=5  n<8  not journal", out)
            self.assertTrue(any("power=low" in w for w in check(parse(path.read_text(), str(path))).warnings))


class TestHarnessAndReceipt(unittest.TestCase):
    def test_summary_stamps_n_and_journal_false(self):
        cfg = VelaConfig(name=CCA, seeds=list(HOUSE))
        summary = _summarize(_passing(HOUSE), cfg)
        self.assertEqual(summary["verdict"], "ACCEPT")
        self.assertEqual(summary["power"], "low")
        self.assertEqual(summary["n_seeds"], 5)
        self.assertIs(summary["journal"], False)
        self.assertIn("not journal", summary["honesty"])

    def test_receipt_cli_prints_power_line(self):
        cfg = VelaConfig(name=CCA, seeds=list(HOUSE))
        summary = _summarize(_passing(HOUSE), cfg)
        summary["config"] = {
            "seeds": list(HOUSE),
            "duration_s": 90.0,
            "scenarios": ["leo_fast_ho", "terrestrial"],
        }
        summary["rows"] = _passing(HOUSE)
        receipt = build_receipt(
            source=_contract_src(HOUSE),
            source_name="house5.vela",
            compose=["Detect", "SoftReprobe", "IntervalBw"],
            config=summary["config"],
            summary=summary,
        )
        self.assertEqual(receipt["power"], "low")
        self.assertEqual(receipt["n_seeds"], 5)
        self.assertIs(receipt["journal"], False)
        with tempfile.TemporaryDirectory() as tmp:
            rp = Path(tmp) / "receipt.json"
            write_receipt(receipt, rp)
            ep = Path(tmp) / "eval.json"
            ep.write_text(json.dumps(summary), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["receipt", str(rp), "--eval", str(ep)])
            self.assertEqual(rc, 0)
            self.assertIn("power=low  n=5  n<8  not journal", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
