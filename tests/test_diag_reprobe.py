"""diag_reprobe plan-only is cheap and honest about flicker extras."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "diag_reprobe.py"


def _load():
    spec = importlib.util.spec_from_file_location("diag_reprobe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestDiagReprobe(unittest.TestCase):
    def test_plan_only_subset(self):
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plan.json"
            rc = mod.main(["--only", "7:45", "--json-out", str(out)])
            self.assertEqual(rc, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(payload["run"])
            self.assertEqual(payload["jobs"], [{"seed": 7, "duration_s": 45.0}])
            self.assertFalse(payload["dual_gate_claim"])
            self.assertIn("flicker", payload["honesty"])

    def test_docs(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("plan-only", text)
        self.assertIn("0.58", text)


if __name__ == "__main__":
    unittest.main()
