"""ablate_seed7 plan is cheap and honest; power helper has no dual-gate claim."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from vela.types import POWER_OK_MIN_SEEDS, power_label_for_seeds


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ablate_seed7.py"


def _load():
    spec = importlib.util.spec_from_file_location("ablate_seed7", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestPowerLabelHelper(unittest.TestCase):
    def test_house_five_is_low_not_dual_gate(self):
        label = power_label_for_seeds([13, 7, 42, 99, 123])
        self.assertEqual(label["n"], 5)
        self.assertEqual(label["power"], "low")
        self.assertIn("Not a dual-gate win", label["note"])
        self.assertIn(f"n<{POWER_OK_MIN_SEEDS}", label["note"])

    def test_eight_seeds_ok(self):
        label = power_label_for_seeds([13, 7, 42, 99, 123, 17, 19, 23])
        self.assertEqual(label["power"], "ok")


class TestAblateSeed7Plan(unittest.TestCase):
    def test_plan_only_is_cheap_and_honest(self):
        ablate = _load()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plan.json"
            rc = ablate.main(
                ["--only", "pass", "chase", "--seeds", "7", "--json-out", str(out)]
            )
            self.assertEqual(rc, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(payload["run"])
            self.assertEqual(payload["variants"], ["pass", "chase"])
            self.assertEqual(payload["gate"], "fast")
            self.assertEqual(payload["power"]["power"], "low")
            self.assertIn("Not a house DualGate claim", payload["honesty"])
            self.assertEqual(payload["results"], [])

    def test_script_surface(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("HorizonChase", text)
        self.assertIn("--only", text)
        self.assertIn("plan-only", text)


if __name__ == "__main__":
    unittest.main()
