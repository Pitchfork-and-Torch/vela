"""--publish must call orbitstack sanitizer. Never naive-copy lab JSON."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP_PATH = ROOT / "scripts" / "space_internet_loop.py"


def _load_loop():
    spec = importlib.util.spec_from_file_location("space_internet_loop", LOOP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {LOOP_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LOOP = _load_loop()


CREST_DEST = {
    "updated": "2026-08-14",
    "title": "OrbitStack / VELA research progress",
    "honesty": (
        "Means only. Do not mix starlink_v1 Crest, OPE-fair v3.7, coupled-RNG v3.4, "
        "or WetLinks CSV in one Current claim. No dish Mbps."
    ),
    "engine": {
        "name": "LeoAware",
        "current": "v3.9 Crest",
        "starlink_v1_crest": {
            "goodput_mbps": 82.07,
            "p95_ms": 76.26,
            "vs": "BBRv3approx 82.44 / 76.66",
            "decision": "ACCEPT",
        },
        "wetlinks_v1_batch": {
            "goodput_mbps": 156.7,
            "p95_ms": 63.98,
            "vs": "BBRv3approx 161.91 / 64.38",
            "decision": "ACCEPT era, not Current",
        },
        "ope_fair_v37": {
            "goodput_mbps": 58.78,
            "p95_ms": 152.09,
            "vs": "BBRv3approx 58.21 / 152.89",
        },
        "lab_coupled_v34": {
            "goodput_mbps": 73.57,
            "p95_ms": 138.37,
            "vs": "BBRv3approx 70.88 / 138.83",
        },
    },
    "language": {
        "name": "VELA",
        "role": "Compose and check LeoAware. Not a rival CCA.",
        "site": "https://vela.jonbailey.xyz/",
    },
    "log": [
        {
            "date": "2026-08-14",
            "note": "JON-14 public means: starlink_v1 Crest 82.07 / 76.26.",
            "verdict": "public-means",
        }
    ],
}

LAB_CLOBBER = {
    "updated": "2026-08-14",
    "honesty": "Means only. Coupled-RNG house numbers. No dish Mbps claim.",
    "engine": {
        "name": "LeoAware",
        "current": "v3.4-p95",
        "lab_coupled_v34": {
            "goodput_mbps": 73.57,
            "p95_ms": 138.37,
            "vs": "BBRv3approx 70.88 / 138.83",
        },
    },
    "log": [
        {
            "date": "2026-08-13",
            "note": "Mission lock: VELA builds onto LeoAware for space internet.",
            "verdict": "policy",
        },
        {
            "date": "2026-08-14",
            "note": "passthrough seed7 45s Leo 88.65/108.4 Reach 88.65/108.4",
            "verdict": "done",
        },
    ],
}


class TestPublishWire(unittest.TestCase):
    def test_source_never_naive_copies(self) -> None:
        text = LOOP_PATH.read_text(encoding="utf-8")
        self.assertIn("publish_progress.py", text)
        self.assertNotIn("dest.write_text(PUBLIC.read_text", text)

    def test_missing_sanitizer_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "lab.json"
            dest = tmp_path / "progress.json"
            src.write_text(json.dumps(LAB_CLOBBER), encoding="utf-8")
            dest.write_text(json.dumps({"engine": {"current": "v3.9 Crest"}}), encoding="utf-8")
            before = dest.read_text(encoding="utf-8")
            code = LOOP.publish(
                src=src, dest=dest, sanitizer=tmp_path / "missing_publish_progress.py"
            )
            self.assertEqual(code, 2)
            self.assertEqual(dest.read_text(encoding="utf-8"), before)

    def test_missing_src_does_not_write(self) -> None:
        sanitizer = Path.home() / "orbitstack" / "scripts" / "publish_progress.py"
        if not sanitizer.is_file():
            self.skipTest("orbitstack sanitizer not on this machine")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dest = tmp_path / "progress.json"
            dest.write_text(json.dumps({"engine": {"current": "v3.9 Crest"}}), encoding="utf-8")
            before = dest.read_text(encoding="utf-8")
            code = LOOP.publish(
                src=tmp_path / "absent.json", dest=dest, sanitizer=sanitizer
            )
            self.assertEqual(code, 2)
            self.assertEqual(dest.read_text(encoding="utf-8"), before)

    def test_publish_keeps_crest_and_drops_lab_notes(self) -> None:
        sanitizer = Path.home() / "orbitstack" / "scripts" / "publish_progress.py"
        if not sanitizer.is_file():
            self.skipTest("orbitstack sanitizer not on this machine")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "lab.json"
            dest = tmp_path / "progress.json"
            src.write_text(json.dumps(LAB_CLOBBER), encoding="utf-8")
            dest.write_text(json.dumps(CREST_DEST), encoding="utf-8")
            code = LOOP.publish(src=src, dest=dest, sanitizer=sanitizer)
            self.assertEqual(code, 0)
            after = json.loads(dest.read_text(encoding="utf-8"))
            self.assertNotEqual(after["engine"]["current"], "v3.4-p95")
            self.assertEqual(after["engine"]["starlink_v1_crest"]["goodput_mbps"], 82.07)
            self.assertEqual(after["engine"]["starlink_v1_crest"]["p95_ms"], 76.26)
            notes = " ".join(row["note"] for row in after["log"])
            self.assertNotIn("passthrough", notes.lower())
            self.assertNotIn("seed7", notes.lower())
            self.assertIn("JON-14", notes)
            self.assertIn("Mission lock", notes)

    def test_publish_dry_run_does_not_write(self) -> None:
        sanitizer = Path.home() / "orbitstack" / "scripts" / "publish_progress.py"
        if not sanitizer.is_file():
            self.skipTest("orbitstack sanitizer not on this machine")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "lab.json"
            dest = tmp_path / "progress.json"
            src.write_text(json.dumps(LAB_CLOBBER), encoding="utf-8")
            dest.write_text(json.dumps(CREST_DEST), encoding="utf-8")
            before = dest.read_text(encoding="utf-8")
            code = LOOP.publish(src=src, dest=dest, sanitizer=sanitizer, dry_run=True)
            self.assertEqual(code, 0)
            self.assertEqual(dest.read_text(encoding="utf-8"), before)

    def test_main_publish_returns_sanitizer_fail(self) -> None:
        from unittest import mock

        with mock.patch.object(LOOP, "publish", return_value=2) as pub:
            code = LOOP.main(["--publish"])
        self.assertEqual(code, 2)
        pub.assert_called_once_with(dry_run=False)

    def test_main_publish_dry_run_flag(self) -> None:
        from unittest import mock

        with mock.patch.object(LOOP, "publish", return_value=0) as pub:
            with mock.patch.object(LOOP, "tick") as tick:
                code = LOOP.main(["--publish", "--dry-run"])
        self.assertEqual(code, 0)
        pub.assert_called_once_with(dry_run=True)
        tick.assert_not_called()

    def test_main_publish_once_skips_tick_on_fail(self) -> None:
        from unittest import mock

        with mock.patch.object(LOOP, "publish", return_value=2):
            with mock.patch.object(LOOP, "tick", return_value=0) as tick:
                code = LOOP.main(["--publish", "--once"])
        self.assertEqual(code, 2)
        tick.assert_not_called()


if __name__ == "__main__":
    unittest.main()
