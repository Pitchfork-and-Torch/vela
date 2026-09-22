"""ablate_seed7 dry-run is cheap, honest, and fail-closed on observe."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from vela.ir import VelaConfig
from vela.types import HOUSE_ENDPOINT_CUT


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ablate_seed7.py"
DIAG = ROOT / "scripts" / "diag_reprobe.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestAblateSeed7DryRun(unittest.TestCase):
    def test_default_is_dry_run_with_required_seeds(self):
        ablate = _load(SCRIPT, "ablate_seed7")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plan.json"
            rc = ablate.main(["--only", "pass", "chase", "--json-out", str(out)])
            self.assertEqual(rc, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(payload["dry_run"])
            self.assertFalse(payload["run"])
            self.assertEqual(payload["variants"], ["pass", "chase"])
            self.assertEqual(payload["seeds"], [7, 13])
            self.assertEqual(payload["soft_reprobe_cut"], HOUSE_ENDPOINT_CUT)
            self.assertIn("SoftFlicker", payload["refused_on_observe"])
            self.assertIn("QuietShield", payload["refused_on_observe"])
            self.assertIn("hop", payload["hop_vs_flicker"])
            self.assertIn("flicker", payload["hop_vs_flicker"])
            self.assertTrue(payload["green_seeds"]["compose_change_allowed"])
            self.assertEqual(payload["results"], [])
            self.assertIn("Not a house DualGate claim", payload["honesty"])

    def test_explicit_dry_run_flag(self):
        ablate = _load(SCRIPT, "ablate_seed7")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plan.json"
            rc = ablate.main(
                ["--dry-run", "--seeds", "7", "--json-out", str(out)]
            )
            self.assertEqual(rc, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["green_seeds"]["missing_required"], [13])
            self.assertFalse(payload["green_seeds"]["compose_change_allowed"])

    def test_run_and_dry_run_conflict(self):
        ablate = _load(SCRIPT, "ablate_seed7")
        rc = ablate.main(["--run", "--dry-run"])
        self.assertEqual(rc, 2)

    def test_refuse_soft_flicker_on_observe(self):
        ablate = _load(SCRIPT, "ablate_seed7")
        bad = VelaConfig(
            soft_flicker=True,
            observe_only=True,
            posture="observe",
            mechanisms=["SoftFlicker"],
        )
        with self.assertRaises(SystemExit) as ctx:
            ablate.refuse_closed_on_observe(bad)
        self.assertIn("SoftFlicker", str(ctx.exception))

    def test_refuse_quiet_shield_on_observe(self):
        ablate = _load(SCRIPT, "ablate_seed7")
        bad = VelaConfig(
            quiet_shield=True,
            observe_only=True,
            posture="observe",
            mechanisms=["QuietShield"],
        )
        with self.assertRaises(SystemExit) as ctx:
            ablate.refuse_closed_on_observe(bad)
        self.assertIn("QuietShield", str(ctx.exception))

    def test_gift_configs_keep_cut_and_refuse_closed(self):
        ablate = _load(SCRIPT, "ablate_seed7")
        cfgs = ablate._configs()
        ablate.assert_gift_configs_safe(cfgs)
        for key, cfg in cfgs.items():
            if cfg is None:
                continue
            self.assertFalse(cfg.soft_flicker, msg=key)
            self.assertFalse(cfg.quiet_shield, msg=key)

    def test_script_documents_laws(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("0.58", text)
        self.assertIn("SoftFlicker", text)
        self.assertIn("QuietShield", text)
        self.assertIn("--dry-run", text)
        self.assertIn("REQUIRED_GREEN_SEEDS", text)
        self.assertIn("hop", text.lower())
        self.assertIn("flicker", text.lower())


class TestDiagReprobeDryRun(unittest.TestCase):
    def test_diag_dry_run_labels_hop_vs_flicker(self):
        diag = _load(DIAG, "diag_reprobe")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "diag.json"
            rc = diag.main(["--dry-run", "--json-out", str(out)])
            self.assertEqual(rc, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["soft_reprobe_cut"], HOUSE_ENDPOINT_CUT)
            self.assertIn("hop", payload["hop_vs_flicker"])
            self.assertIn("flicker", payload["hop_vs_flicker"])
            self.assertIn("SoftFlicker", payload["refused_on_observe"])


if __name__ == "__main__":
    unittest.main()
