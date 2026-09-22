"""--publish must call orbitstack sanitizer. Never naive-copy lab JSON.
Safer --once: safe pending only, dry-run does not mutate lab, logs under results/.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
            "note": "Public means: starlink_v1 Crest 82.07 / 76.26.",
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
        self.assertIn("Never naive-copy", text)

    def test_missing_sanitizer_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "lab.json"
            dest = tmp_path / "progress.json"
            src.write_text(json.dumps(LAB_CLOBBER), encoding="utf-8")
            dest.write_text(json.dumps({"engine": {"current": "v3.9 Crest"}}), encoding="utf-8")
            before = dest.read_text(encoding="utf-8")
            with mock.patch.object(LOOP, "RESULTS", tmp_path / "results"):
                with mock.patch.object(LOOP, "LOOP_LOG", tmp_path / "results" / "loop_ticks.jsonl"):
                    with mock.patch.object(LOOP, "LOOP_LAST", tmp_path / "results" / "loop_last.json"):
                        code = LOOP.publish(
                            src=src,
                            dest=dest,
                            sanitizer=tmp_path / "missing_publish_progress.py",
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
            with mock.patch.object(LOOP, "RESULTS", tmp_path / "results"):
                with mock.patch.object(LOOP, "LOOP_LOG", tmp_path / "results" / "loop_ticks.jsonl"):
                    with mock.patch.object(LOOP, "LOOP_LAST", tmp_path / "results" / "loop_last.json"):
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
            with mock.patch.object(LOOP, "RESULTS", tmp_path / "results"):
                with mock.patch.object(LOOP, "LOOP_LOG", tmp_path / "results" / "loop_ticks.jsonl"):
                    with mock.patch.object(LOOP, "LOOP_LAST", tmp_path / "results" / "loop_last.json"):
                        code = LOOP.publish(src=src, dest=dest, sanitizer=sanitizer)
            self.assertEqual(code, 0)
            after = json.loads(dest.read_text(encoding="utf-8"))
            self.assertNotEqual(after["engine"]["current"], "v3.4-p95")
            self.assertEqual(after["engine"]["starlink_v1_crest"]["goodput_mbps"], 82.07)
            self.assertEqual(after["engine"]["starlink_v1_crest"]["p95_ms"], 76.26)
            notes = " ".join(row["note"] for row in after["log"])
            self.assertNotIn("passthrough", notes.lower())
            self.assertNotIn("seed7", notes.lower())
            self.assertIn("Public means", notes)
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
            with mock.patch.object(LOOP, "RESULTS", tmp_path / "results"):
                with mock.patch.object(LOOP, "LOOP_LOG", tmp_path / "results" / "loop_ticks.jsonl"):
                    with mock.patch.object(LOOP, "LOOP_LAST", tmp_path / "results" / "loop_last.json"):
                        code = LOOP.publish(
                            src=src, dest=dest, sanitizer=sanitizer, dry_run=True
                        )
            self.assertEqual(code, 0)
            self.assertEqual(dest.read_text(encoding="utf-8"), before)

    def test_main_publish_returns_sanitizer_fail(self) -> None:
        with mock.patch.object(LOOP, "publish", return_value=2) as pub:
            code = LOOP.main(["--publish"])
        self.assertEqual(code, 2)
        pub.assert_called_once_with(dry_run=False)

    def test_main_publish_dry_run_flag(self) -> None:
        with mock.patch.object(LOOP, "publish", return_value=0) as pub:
            with mock.patch.object(LOOP, "tick") as tick:
                code = LOOP.main(["--publish", "--dry-run"])
        self.assertEqual(code, 0)
        pub.assert_called_once_with(dry_run=True)
        tick.assert_not_called()

    def test_main_publish_once_skips_tick_on_fail(self) -> None:
        with mock.patch.object(LOOP, "publish", return_value=2):
            with mock.patch.object(LOOP, "tick", return_value=0) as tick:
                code = LOOP.main(["--publish", "--once"])
        self.assertEqual(code, 2)
        tick.assert_not_called()

    def test_main_requires_once_or_publish(self) -> None:
        code = LOOP.main([])
        self.assertEqual(code, 2)


class TestSafeOnce(unittest.TestCase):
    def _lab(self, tmp: Path, items: list[dict]) -> None:
        lab = tmp / "lab"
        results = tmp / "results"
        lab.mkdir()
        results.mkdir()
        (lab / "BACKLOG.json").write_text(
            json.dumps({"items": items}, indent=2) + "\n", encoding="utf-8"
        )
        (lab / "STATE.md").write_text("# Loop state\n\nstatus: ok\n", encoding="utf-8")
        (lab / "PUBLIC_PROGRESS.json").write_text(
            json.dumps({"updated": "2026-09-22", "log": []}, indent=2) + "\n",
            encoding="utf-8",
        )
        (lab / "journal.jsonl").write_text("", encoding="utf-8")
        self.lab = lab
        self.results = results
        self.patches = [
            mock.patch.object(LOOP, "LAB", lab),
            mock.patch.object(LOOP, "BACKLOG", lab / "BACKLOG.json"),
            mock.patch.object(LOOP, "STATE", lab / "STATE.md"),
            mock.patch.object(LOOP, "JOURNAL", lab / "journal.jsonl"),
            mock.patch.object(LOOP, "PUBLIC", lab / "PUBLIC_PROGRESS.json"),
            mock.patch.object(LOOP, "STOP", lab / "STOP"),
            mock.patch.object(LOOP, "RESULTS", results),
            mock.patch.object(LOOP, "LOOP_LOG", results / "loop_ticks.jsonl"),
            mock.patch.object(LOOP, "LOOP_LAST", results / "loop_last.json"),
        ]

    def test_next_item_skips_unsafe_and_closed_write(self) -> None:
        data = {
            "items": [
                {
                    "id": "unsafe-thing",
                    "kind": "language",
                    "safe": False,
                    "status": "pending",
                    "note": "nope",
                },
                {
                    "id": "enable-closed-write-chase",
                    "kind": "language",
                    "safe": True,
                    "status": "pending",
                    "note": "Enable closed-write HorizonChase without green ablation",
                },
                {
                    "id": "kernel-only",
                    "kind": "kernel",
                    "safe": True,
                    "status": "pending",
                    "note": "not actuator-known",
                },
                {
                    "id": "path-realism-rails",
                    "kind": "language",
                    "safe": True,
                    "status": "pending",
                    "note": "Path realism",
                },
            ]
        }
        nxt = LOOP._next_item(data)
        assert nxt is not None
        self.assertEqual(nxt["id"], "path-realism-rails")

    def test_dry_run_once_does_not_mutate_lab(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._lab(
                tmp_path,
                [
                    {
                        "id": "path-realism-rails",
                        "kind": "language",
                        "safe": True,
                        "public": True,
                        "note": "Path realism rails",
                        "status": "pending",
                    }
                ],
            )
            backlog_before = (self.lab / "BACKLOG.json").read_text(encoding="utf-8")
            state_before = (self.lab / "STATE.md").read_text(encoding="utf-8")
            public_before = (self.lab / "PUBLIC_PROGRESS.json").read_text(encoding="utf-8")
            journal_before = (self.lab / "journal.jsonl").read_text(encoding="utf-8")
            for p in self.patches:
                p.start()
            try:
                code = LOOP.main(["--once", "--dry-run"])
            finally:
                for p in self.patches:
                    p.stop()
            self.assertEqual(code, 0)
            self.assertEqual(
                (self.lab / "BACKLOG.json").read_text(encoding="utf-8"), backlog_before
            )
            self.assertEqual((self.lab / "STATE.md").read_text(encoding="utf-8"), state_before)
            self.assertEqual(
                (self.lab / "PUBLIC_PROGRESS.json").read_text(encoding="utf-8"),
                public_before,
            )
            self.assertEqual(
                (self.lab / "journal.jsonl").read_text(encoding="utf-8"), journal_before
            )
            last = json.loads((self.results / "loop_last.json").read_text(encoding="utf-8"))
            self.assertTrue(last["dry_run"])
            self.assertEqual(last["id"], "path-realism-rails")
            self.assertTrue((self.results / "loop_ticks.jsonl").is_file())

    def test_once_language_queues_needs_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._lab(
                tmp_path,
                [
                    {
                        "id": "hint-ingress-fail-closed",
                        "kind": "language",
                        "safe": True,
                        "public": True,
                        "note": "Hint ingress fail-closed",
                        "status": "pending",
                    }
                ],
            )
            for p in self.patches:
                p.start()
            try:
                code = LOOP.main(["--once"])
            finally:
                for p in self.patches:
                    p.stop()
            self.assertEqual(code, 0)
            data = json.loads((self.lab / "BACKLOG.json").read_text(encoding="utf-8"))
            self.assertEqual(data["items"][0]["status"], "needs_agent")
            last = json.loads((self.results / "loop_last.json").read_text(encoding="utf-8"))
            self.assertEqual(last["event"], "tick")
            self.assertEqual(last["status"], "needs_agent")
            public = json.loads((self.lab / "PUBLIC_PROGRESS.json").read_text(encoding="utf-8"))
            self.assertTrue(public["log"])


class TestBacklogStarlinkItems(unittest.TestCase):
    def test_repo_backlog_has_safe_pending_starlink_items(self) -> None:
        data = json.loads((ROOT / "lab" / "BACKLOG.json").read_text(encoding="utf-8"))
        by_id = {it["id"]: it for it in data["items"]}
        for done in ("path-realism-rails", "hint-ingress-fail-closed"):
            self.assertEqual(by_id[done]["status"], "done", done)
            self.assertEqual(by_id[done].get("pr"), 28, done)
        pending = [
            it
            for it in data["items"]
            if it.get("status") == "pending" and it.get("safe") is True
        ]
        ids = {it["id"] for it in pending}
        for need in (
            "dual-gate-honesty-label",
            "power-label-surface",
        ):
            self.assertIn(need, ids)
        for it in pending:
            self.assertIn(it["kind"], ("language", "eval"))
            self.assertNotIn("enable closed-write", (it.get("note") or "").lower())


if __name__ == "__main__":
    unittest.main()
