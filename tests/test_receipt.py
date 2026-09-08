"""Receipt verify binds source, config, path, and seed rows."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.cli import main
from vela.eval_harness import parse_worker_stdout
from vela.ir import program_to_config
from vela.parser import parse
from vela.receipt import (
    build_receipt,
    eval_gate,
    rows_merkle,
    verify_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def _row(gp: float = 88.65, p95: float = 108.4, seed: int = 7) -> dict:
    return {
        "scenario": "leo_fast_ho",
        "seed": seed,
        "cca": "Reach",
        "goodput_mbps": gp,
        "p95_rtt_ms": p95,
    }


def _summary(**kw) -> dict:
    rows = kw.pop("rows", [_row()])
    config = kw.pop(
        "config",
        {
            "name": "Reach",
            "seeds": [13, 7],
            "scenarios": ["leo_fast_ho", "terrestrial"],
            "duration_s": 45.0,
        },
    )
    base = {
        "verdict": "INCOMPLETE",
        "power": "low",
        "gate": "fast",
        "honesty": "test",
        "rows": rows,
        "config": config,
    }
    base.update(kw)
    return base


def _receipt(src: str | None = None, summary: dict | None = None):
    src = src if src is not None else (EX / "reach.vela").read_text(encoding="utf-8")
    summary = summary if summary is not None else _summary()
    cfg = program_to_config(parse(src, "reach.vela"))
    rec = build_receipt(
        source=src,
        source_name="reach.vela",
        compose=list(cfg.mechanisms),
        config=summary["config"],
        summary=summary,
    )
    return rec, src, summary


class TestEvalGate(unittest.TestCase):
    def test_house_vs_fast_vs_named(self):
        self.assertEqual(
            eval_gate([13, 7, 42, 99, 123], 90.0, ["leo_fast_ho", "terrestrial"]),
            "house",
        )
        self.assertEqual(eval_gate([13, 7], 45.0, ["leo_fast_ho", "terrestrial"]), "fast")
        self.assertEqual(eval_gate([7], 90.0, ["leo_fast_ho"]), "named")

    def test_house_needs_terrestrial(self):
        self.assertEqual(
            eval_gate([13, 7, 42, 99, 123], 90.0, ["leo_fast_ho"]),
            "named",
        )


class TestReceiptVerify(unittest.TestCase):
    def test_roundtrip_with_eval_bound(self):
        rec, src, summary = _receipt()
        self.assertEqual(verify_receipt(rec, source=src), [])
        self.assertEqual(verify_receipt(rec, source=src, summary=summary), [])
        self.assertEqual(rec["gate"], "fast")
        self.assertEqual(rec["n_rows"], 1)

    def test_swapped_number_fails_when_rows_bound(self):
        rec, src, summary = _receipt()
        self.assertEqual(verify_receipt(rec, source=src), [])
        summary["rows"][0]["goodput_mbps"] = 99.99
        errs = verify_receipt(rec, source=src, summary=summary)
        self.assertTrue(any("rows_merkle" in e for e in errs), errs)

    def test_swapped_number_does_not_fail_unbound(self):
        rec, src, summary = _receipt()
        summary["rows"][0]["goodput_mbps"] = 99.99
        self.assertEqual(verify_receipt(rec, source=src), [])

    def test_verdict_swap_fails_digest(self):
        rec, src, _ = _receipt()
        rec["verdict"] = "ACCEPT"
        self.assertTrue(verify_receipt(rec, source=src))

    def test_verdict_mismatch_vs_eval(self):
        rec, src, summary = _receipt()
        summary["verdict"] = "ACCEPT"
        errs = verify_receipt(rec, source=src, summary=summary)
        self.assertTrue(any("verdict" in e for e in errs), errs)

    def test_config_swap_fails_when_bound(self):
        rec, src, summary = _receipt()
        summary["config"] = dict(summary["config"])
        summary["config"]["duration_s"] = 90.0
        errs = verify_receipt(rec, source=src, summary=summary)
        self.assertTrue(any("config_digest" in e for e in errs), errs)

    def test_source_swap_fails(self):
        rec, _, summary = _receipt()
        other = (EX / "equinox.vela").read_text(encoding="utf-8")
        errs = verify_receipt(rec, source=other, summary=summary)
        self.assertTrue(any("source_digest" in e for e in errs), errs)

    def test_gate_must_match_config(self):
        rec, src, summary = _receipt()
        rec["gate"] = "house"
        rec.pop("receipt_digest")
        from vela.digest import tagged

        clone = {k: v for k, v in rec.items()}
        rec["receipt_digest"] = tagged(
            "receipt",
            json.dumps(clone, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        )
        errs = verify_receipt(rec, source=src, summary=summary)
        self.assertTrue(any("gate" in e for e in errs), errs)

    def test_n_rows_mismatch(self):
        rec, src, summary = _receipt()
        summary["rows"] = [_row(), _row(seed=13)]
        # merkle will also fail; n_rows is the count rail
        errs = verify_receipt(rec, source=src, rows=summary["rows"])
        self.assertTrue(any("n_rows" in e for e in errs), errs)
        self.assertTrue(any("rows_merkle" in e for e in errs), errs)

    def test_rows_merkle_stable(self):
        a = rows_merkle([_row(88.65), _row(70.0, seed=13)])
        b = rows_merkle([_row(88.65), _row(70.0, seed=13)])
        c = rows_merkle([_row(88.66), _row(70.0, seed=13)])
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class TestReceiptCli(unittest.TestCase):
    def test_cli_unbound_ok_and_bound_catches_swap(self):
        rec, src, summary = _receipt()
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            receipt_path = td / "receipt.json"
            eval_path = td / "eval.json"
            src_path = td / "reach.vela"
            receipt_path.write_text(json.dumps(rec), encoding="utf-8")
            src_path.write_text(src, encoding="utf-8")
            eval_path.write_text(json.dumps(summary), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["receipt", str(receipt_path), "--source", str(src_path)])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("rows=unbound", out)
            self.assertIn("pass --eval", out)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(
                    [
                        "receipt",
                        str(receipt_path),
                        "--source",
                        str(src_path),
                        "--eval",
                        str(eval_path),
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertIn("rows=bound", buf.getvalue())
            summary["rows"][0]["goodput_mbps"] = 1.0
            eval_path.write_text(json.dumps(summary), encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(
                    [
                        "receipt",
                        str(receipt_path),
                        "--source",
                        str(src_path),
                        "--eval",
                        str(eval_path),
                    ]
                )
            self.assertEqual(rc, 1)
            self.assertIn("rows_merkle", buf.getvalue())


class TestWorkerStdout(unittest.TestCase):
    def test_ignores_log_lines_before_row(self):
        text = (
            "leo_fast_ho seed=7 Reach ...\n"
            "warning: cache miss\n"
            '{"goodput_mbps": 88.65, "p95_rtt_ms": 108.4, "cca": "Reach"}\n'
        )
        rec = parse_worker_stdout(text)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["goodput_mbps"], 88.65)

    def test_empty_or_garbage_is_none(self):
        self.assertIsNone(parse_worker_stdout(""))
        self.assertIsNone(parse_worker_stdout("not json\n{bad"))


if __name__ == "__main__":
    unittest.main()
