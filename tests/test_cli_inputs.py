"""CLI input errors are one `error:` line and exit 2, not a traceback."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.cli import main

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    return rc, buf.getvalue()


class TestMissingProgram(unittest.TestCase):
    def test_every_program_subcommand_reports_missing_file(self):
        for cmd in ("check", "compile", "digest", "emit-rust", "eval"):
            rc, out = _run([cmd, "no_such_program.vela"])
            self.assertEqual(rc, 2, (cmd, out))
            self.assertIn("error: cannot read program", out, cmd)
            self.assertIn("no_such_program.vela", out, cmd)
            self.assertNotIn("Traceback", out, cmd)

    def test_binary_program_is_reported_not_decoded(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bin.vela"
            bad.write_bytes(b"\xff\xfe\x00")
            rc, out = _run(["check", str(bad)])
        self.assertEqual(rc, 2, out)
        self.assertIn("not UTF-8", out)


class TestReceiptInputs(unittest.TestCase):
    def test_missing_receipt_file(self):
        rc, out = _run(["receipt", "no_such_receipt.json"])
        self.assertEqual(rc, 2, out)
        self.assertIn("error: cannot read receipt", out)

    def test_malformed_receipt_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "receipt.json"
            bad.write_text("{bad", encoding="utf-8")
            rc, out = _run(["receipt", str(bad)])
        self.assertEqual(rc, 2, out)
        self.assertIn("is not valid JSON", out)
        self.assertIn("line 1", out)

    def test_non_object_receipt_is_a_verify_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "receipt.json"
            bad.write_text("[]", encoding="utf-8")
            rc, out = _run(["receipt", str(bad)])
        self.assertEqual(rc, 1, out)
        self.assertIn("error: receipt is not a JSON object", out)

    def test_missing_source_and_eval_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            rec = td / "receipt.json"
            rec.write_text(json.dumps({"domain": "VELA1", "alg": "sha256"}), encoding="utf-8")
            rc, out = _run(["receipt", str(rec), "--source", str(td / "gone.vela")])
            self.assertEqual(rc, 2, out)
            self.assertIn("error: cannot read source", out)
            rc, out = _run(["receipt", str(rec), "--eval", str(td / "gone.json")])
            self.assertEqual(rc, 2, out)
            self.assertIn("error: cannot read eval JSON", out)

    def test_non_object_eval_summary_is_a_verify_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            rec = td / "receipt.json"
            rec.write_text(json.dumps({"domain": "VELA1", "alg": "sha256"}), encoding="utf-8")
            ev = td / "eval.json"
            ev.write_text("[]", encoding="utf-8")
            rc, out = _run(["receipt", str(rec), "--eval", str(ev)])
        self.assertEqual(rc, 1, out)
        self.assertIn("eval summary is not a JSON object", out)

    def test_good_program_still_checks(self):
        rc, out = _run(["check", str(EX / "reach.vela")])
        self.assertEqual(rc, 0, out)
        self.assertIn("passthrough", out)


if __name__ == "__main__":
    unittest.main()
