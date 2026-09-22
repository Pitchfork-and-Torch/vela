"""Compose digest / views law: refuse claiming compose A as compose B."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.cli import main
from vela.digest import compose_digest
from vela.ir import program_to_config
from vela.parser import parse
from vela.receipt import bind_compose_to_source, build_receipt, verify_receipt

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def _summary(view: str = "") -> dict:
    return {
        "verdict": "INCOMPLETE",
        "power": "low",
        "honesty": "test",
        "gate": "named",
        "rows": [],
        "config": {
            "name": "Equinox" if not view else f"Equinox/{view}",
            "view": view,
            "seeds": [7],
            "duration_s": 45.0,
            "scenarios": ["leo_fast_ho"],
        },
    }


class TestComposeViewsLaw(unittest.TestCase):
    def test_reach_check_prints_compose_hex(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", str(EX / "reach.vela")])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        # Flagship Reach must show the compose digest (not a vague digest=).
        self.assertRegex(out, r"(?m)^\s*compose_digest=[0-9a-f]{16}\s*$")
        self.assertNotRegex(out, r"(?m)^\s*digest=")

    def test_equinox_check_prints_view_compose(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", str(EX / "equinox.vela")])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertRegex(out, r"compose_digest=[0-9a-f]{16}")
        self.assertIn("views=Observe", out)
        self.assertRegex(out, r"view Observe compose_digest=[0-9a-f]{16}")
        # Controller compose and Observe view must differ (WriteBudget).
        src = (EX / "equinox.vela").read_text(encoding="utf-8")
        prog = parse(src, "equinox.vela")
        base_hex = compose_digest(prog.controllers[0].compose)[:16]
        view_hex = compose_digest(prog.views[0].compose)[:16]
        self.assertNotEqual(base_hex, view_hex)
        self.assertIn(f"compose_digest={base_hex}", out)
        self.assertIn(f"view Observe compose_digest={view_hex}", out)

    def test_receipt_stamps_view(self):
        src = (EX / "equinox.vela").read_text(encoding="utf-8")
        prog = parse(src, "equinox.vela")
        cfg = program_to_config(prog, view="Observe")
        summary = _summary(view="Observe")
        summary["config"]["compose_digest"] = cfg.compose_digest
        rec = build_receipt(
            source=src,
            source_name="equinox.vela",
            compose=list(cfg.mechanisms),
            config=summary["config"],
            summary=summary,
        )
        self.assertEqual(rec.get("view"), "Observe")
        self.assertEqual(verify_receipt(rec, source=src), [])

    def test_refuse_view_compose_as_controller(self):
        src = (EX / "equinox.vela").read_text(encoding="utf-8")
        prog = parse(src, "equinox.vela")
        obs = list(prog.views[0].compose)
        summary = _summary(view="")
        rec = build_receipt(
            source=src,
            source_name="equinox.vela",
            compose=obs,
            config=summary["config"],
            summary=summary,
        )
        errs = verify_receipt(rec, source=src)
        self.assertTrue(any("view Observe" in e for e in errs), errs)
        self.assertTrue(any("controller" in e for e in errs), errs)

    def test_refuse_controller_compose_as_view(self):
        src = (EX / "equinox.vela").read_text(encoding="utf-8")
        prog = parse(src, "equinox.vela")
        base = list(prog.controllers[0].compose)
        summary = _summary(view="Observe")
        rec = build_receipt(
            source=src,
            source_name="equinox.vela",
            compose=base,
            config=summary["config"],
            summary=summary,
        )
        errs = verify_receipt(rec, source=src)
        self.assertTrue(any("views law" in e for e in errs), errs)

    def test_refuse_silent_operator_swap(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        prog = parse(src, "reach.vela")
        bad = list(prog.controllers[0].compose)
        # SoftFlicker is review; swapping it in is a silent operator swap.
        self.assertIn("SoftReprobe", bad)
        bad[bad.index("SoftReprobe")] = "SoftFlicker"
        summary = _summary(view="")
        summary["config"]["name"] = "Reach"
        rec = build_receipt(
            source=src,
            source_name="reach.vela",
            compose=bad,
            config=summary["config"],
            summary=summary,
        )
        errs = verify_receipt(rec, source=src)
        self.assertTrue(any("silent operator swap" in e for e in errs), errs)

    def test_bind_helper_direct(self):
        src = (EX / "equinox.vela").read_text(encoding="utf-8")
        prog = parse(src, "equinox.vela")
        self.assertEqual(
            bind_compose_to_source(list(prog.controllers[0].compose), src, view=None),
            [],
        )
        self.assertEqual(
            bind_compose_to_source(list(prog.views[0].compose), src, view="Observe"),
            [],
        )
        errs = bind_compose_to_source(["Detect"], src, view=None)
        self.assertTrue(errs)


if __name__ == "__main__":
    unittest.main()
