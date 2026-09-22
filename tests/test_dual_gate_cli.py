"""CLI/receipt stamp dual_gate_claim so gate=fast ACCEPT is not a house win.

Deepens open #35 (summary/honesty/receipt body) with the remaining human
CLI visibility: gate_cli_line and `vela receipt` print dual_gate_claim=.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.cli import main as vela_main
from vela.eval_harness import _summarize, honesty_text
from vela.ir import VelaConfig, program_to_config
from vela.parser import parse
from vela.receipt import build_receipt, gate_cli_line
from vela.types import HOUSE_ENDPOINT_CUT, dual_gate_claim

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
HOUSE = [13, 7, 42, 99, 123]


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


class TestDualGateCliStamp(unittest.TestCase):
    def test_softreprobe_cut_held(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_helper_false_on_fast_accept(self):
        self.assertFalse(dual_gate_claim("fast", "ACCEPT"))
        self.assertFalse(dual_gate_claim("fast", "FAIL"))
        self.assertTrue(dual_gate_claim("house", "ACCEPT"))
        self.assertFalse(dual_gate_claim("house", "FAIL"))

    def test_gate_cli_line_stamps_claim_bit(self):
        fast = gate_cli_line("fast", "ACCEPT")
        self.assertIn("gate=fast", fast)
        self.assertIn("dual_gate_claim=false", fast)
        self.assertIn("not a dual-gate win", fast)
        house = gate_cli_line("house", "ACCEPT")
        self.assertIn("gate=house", house)
        self.assertIn("dual_gate_claim=true", house)
        self.assertNotIn("not a dual-gate win", house)
        planned = gate_cli_line("fast")
        self.assertIn("dual_gate_claim=false", planned)

    def test_fast_accept_summary_not_house_claim(self):
        seeds = [13, 7]
        cfg = VelaConfig(name="Reach", seeds=list(seeds), duration_s=45.0)
        rows = (
            _rows("leo_fast_ho", "Reach", 80.0, 120.0, seeds)
            + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0, seeds)
            + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0, seeds)
            + _rows("terrestrial", "Reach", 78.0, 40.0, seeds)
        )
        summary = _summarize(rows, cfg, duration_s=45.0)
        self.assertEqual(summary["gate"], "fast")
        self.assertEqual(summary["verdict"], "ACCEPT")
        self.assertFalse(summary["dual_gate_claim"])
        self.assertIn("dual_gate_claim=false", summary["honesty"])
        self.assertIn("dual_gate_claim=false", gate_cli_line("fast", "ACCEPT"))

    def test_house_accept_may_claim(self):
        cfg = VelaConfig(name="Reach", seeds=list(HOUSE), duration_s=90.0)
        rows = (
            _rows("leo_fast_ho", "Reach", 80.0, 120.0)
            + _rows("leo_fast_ho", "BBRv3approx", 70.0, 130.0)
            + _rows("leo_fast_ho", "LeoAware", 80.0, 120.0)
            + _rows("terrestrial", "Reach", 78.0, 40.0)
        )
        summary = _summarize(rows, cfg, duration_s=90.0)
        self.assertEqual(summary["gate"], "house")
        self.assertEqual(summary["verdict"], "ACCEPT")
        self.assertTrue(summary["dual_gate_claim"])
        self.assertIn("dual_gate_claim=true", honesty_text("house", "ACCEPT"))

    def test_receipt_body_and_cli_print_claim(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        cfg = program_to_config(parse(src, "reach.vela"))
        summary = {
            "verdict": "ACCEPT",
            "power": "low",
            "gate": "fast",
            "dual_gate_claim": False,
            "honesty": "dual_gate_claim=false",
            "rows": [
                {
                    "scenario": "leo_fast_ho",
                    "seed": 7,
                    "cca": "Reach",
                    "goodput_mbps": 88.65,
                    "p95_rtt_ms": 108.4,
                }
            ],
            "config": {
                "name": "Reach",
                "seeds": [13, 7],
                "scenarios": ["leo_fast_ho", "terrestrial"],
                "duration_s": 45.0,
            },
        }
        rec = build_receipt(
            source=src,
            source_name="reach.vela",
            compose=list(cfg.mechanisms),
            config=summary["config"],
            summary=summary,
        )
        self.assertIn("dual_gate_claim", rec)
        self.assertFalse(rec["dual_gate_claim"])

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "receipt.json"
            path.write_text(json.dumps(rec), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vela_main(["receipt", str(path)])
            out = buf.getvalue()
            self.assertEqual(rc, 0, out)
            self.assertIn("gate=fast", out)
            self.assertIn("dual_gate_claim=false", out)

    def test_cli_lists_dual_gate_claim_dump_key(self):
        src = (ROOT / "vela" / "cli.py").read_text(encoding="utf-8")
        self.assertIn('"dual_gate_claim"', src)


if __name__ == "__main__":
    unittest.main()
