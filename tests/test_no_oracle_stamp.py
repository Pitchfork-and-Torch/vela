"""no-oracle stamp: crystal-clear refuse of next_capacity / future PathState.

Visibility on Reach check and on house eval receipts/CLI. Complements
calendar-p_ho=past-gaps (#59) without duplicating that Calendar stamp.
"""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main as vela_main
from vela.ir import program_to_config
from vela.oracle import (
    NO_ORACLE_CHECK_LINE,
    NO_ORACLE_RECEIPT_NOTE,
    NO_ORACLE_STAMP,
    oracle_error,
)
from vela.parser import parse
from vela.receipt import (
    build_receipt,
    eval_gate,
    no_oracle_cli_token,
)
from vela.types import HOUSE_ENDPOINT_CUT

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

OLD_CHECK_LINE = "no-oracle  (endpoint cannot see next_capacity)"


class TestStampConstants(unittest.TestCase):
    def test_stamp_names_refuse(self):
        self.assertEqual(NO_ORACLE_STAMP, "no-oracle")
        self.assertIn("refuse next_capacity", NO_ORACLE_CHECK_LINE)
        self.assertIn("future PathState", NO_ORACLE_CHECK_LINE)
        self.assertEqual(NO_ORACLE_RECEIPT_NOTE, "refuse next_capacity / future PathState")
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)


class TestReachCheckStamp(unittest.TestCase):
    def test_reach_is_no_oracle(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.no_oracle)

    def test_reach_check_prints_crystal_clear_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(NO_ORACLE_CHECK_LINE, out)
        self.assertIn("refuse next_capacity / future PathState", out)
        self.assertNotIn(OLD_CHECK_LINE, out)

    def test_horizon_check_prints_crystal_clear_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "horizon.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(NO_ORACLE_CHECK_LINE, out)

    def test_next_capacity_refused_with_no_oracle_law(self):
        src = """
lang vela 0.1
controller Probe {
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
  on Reconfig(e) match e {
    RttHop => {
      pace = next_capacity
    }
    Flicker => hold
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "oracle.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.no_oracle)
        self.assertIn(oracle_error("Probe", "next_capacity"), res.errors)
        joined = "\n".join(res.errors)
        self.assertIn("future PathState", joined)
        self.assertIn("no-oracle", joined)


class TestReceiptHouseVisibility(unittest.TestCase):
    def test_cli_token(self):
        self.assertEqual(no_oracle_cli_token(True), "no-oracle=true")
        self.assertEqual(no_oracle_cli_token(False), "no-oracle=false")

    def test_house_receipt_carries_no_oracle(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        cfg = program_to_config(parse(src, "reach.vela"))
        config = {
            "name": "Reach",
            "seeds": [13, 7, 42, 99, 123],
            "scenarios": ["leo_fast_ho", "terrestrial"],
            "duration_s": 90.0,
            "no_oracle": True,
            "paths": list(cfg.paths or []),
            "path_digest": cfg.path_digest,
        }
        summary = {
            "verdict": "INCOMPLETE",
            "power": "ok",
            "gate": "house",
            "honesty": "test",
            "rows": [],
            "config": config,
        }
        self.assertEqual(eval_gate(config["seeds"], 90.0, config["scenarios"]), "house")
        rec = build_receipt(
            source=src,
            source_name="reach.vela",
            compose=list(cfg.mechanisms),
            config=config,
            summary=summary,
        )
        self.assertTrue(rec.get("no_oracle"))
        self.assertEqual(rec["gate"], "house")

    def test_receipt_cli_prints_no_oracle(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        cfg = program_to_config(parse(src, "reach.vela"))
        config = {
            "name": "Reach",
            "seeds": [13, 7, 42, 99, 123],
            "scenarios": ["leo_fast_ho", "terrestrial"],
            "duration_s": 90.0,
            "no_oracle": True,
            "paths": list(cfg.paths or []),
            "path_digest": cfg.path_digest,
        }
        summary = {
            "verdict": "INCOMPLETE",
            "power": "ok",
            "gate": "house",
            "honesty": "test",
            "rows": [],
            "config": config,
        }
        rec = build_receipt(
            source=src,
            source_name="reach.vela",
            compose=list(cfg.mechanisms),
            config=config,
            summary=summary,
        )
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "receipt_house.json"
            path.write_text(json.dumps(rec), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vela_main(["receipt", str(path)])
            out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("no-oracle=true", out)
        self.assertIn("gate=house", out)


class TestDocs(unittest.TestCase):
    def test_language_names_crystal_clear_stamp(self):
        text = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("refuse next_capacity / future PathState", text)
        self.assertIn("no_oracle=true", text)
        self.assertIn("House eval receipts", text)

    def test_ingress_names_crystal_clear_stamp(self):
        text = (ROOT / "docs" / "INGRESS.md").read_text(encoding="utf-8")
        self.assertIn("refuse next_capacity / future PathState", text)
        self.assertIn("no_oracle=true", text)


if __name__ == "__main__":
    unittest.main()
