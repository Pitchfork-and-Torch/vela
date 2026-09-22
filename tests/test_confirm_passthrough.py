"""confirm_passthrough plan-only is cheap and refuses DualGate claims."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "confirm_passthrough.py"


def _load():
    spec = importlib.util.spec_from_file_location("confirm_passthrough", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestConfirmPassthrough(unittest.TestCase):
    def test_plan_only(self):
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plan.json"
            rc = mod.main(["--json-out", str(out)])
            self.assertEqual(rc, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(payload["run"])
            self.assertEqual(payload["gate"], "fast")
            self.assertFalse(payload["dual_gate_claim"])
            self.assertIn("not the house gate", payload["honesty"])
            self.assertEqual(payload["results"], {})

    def test_script_docs(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("plan-only", text)
        self.assertIn("--run", text)
        self.assertIn("DualGate", text)


if __name__ == "__main__":
    unittest.main()
