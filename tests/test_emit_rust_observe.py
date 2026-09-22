"""emit_rust / digest honesty for observe-only Reach."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.cli import main
from vela.emit_rust import EmitRustError, emit_rust
from vela.parser import parse
from vela.types import HOUSE_ENDPOINT_CUT


ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


class TestEmitRustObserve(unittest.TestCase):
    def test_reach_emit_stamps_observe_honesty(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        text = emit_rust(parse(src, "reach.vela"))
        self.assertIn("observe_only: true", text)
        self.assertIn('posture: "observe"', text)
        self.assertIn("passthrough: true", text)
        self.assertIn("typed_reconfig: true", text)
        self.assertIn("typed_loss: true", text)
        self.assertIn(f"house_endpoint_cut: {HOUSE_ENDPOINT_CUT}", text)
        self.assertIn("horizon_chase: false", text)
        self.assertIn("soft_flicker: false", text)
        self.assertIn("quiet_reach: false", text)
        self.assertIn("Mech enum is a catalog", text)
        self.assertIn("Do not claim a dual-gate win", text)
        self.assertIn("SoftReprobe house cut is 0.58", text)
        # Closed-write names may appear in the catalog enum, but Reach
        # compose must not list them as enabled mechs.
        self.assertIn("Mech::Detect", text)
        self.assertIn("Mech::SoftReprobe", text)
        mechs_block = text.split("mechs: &[")[1].split("]")[0]
        self.assertNotIn("Mech::HorizonChase", mechs_block)
        self.assertNotIn("Mech::SoftFlicker", mechs_block)
        self.assertNotIn("Mech::QuietReach", mechs_block)

    def test_equinox_emit_is_observe_only(self):
        src = (EX / "equinox.vela").read_text(encoding="utf-8")
        text = emit_rust(parse(src, "equinox.vela"))
        self.assertIn("observe_only: true", text)
        self.assertIn('posture: "observe"', text)
        self.assertIn("typed_reconfig: true", text)
        self.assertIn("typed_loss: true", text)

    def test_review_softflicker_emit_does_not_pretend_observe(self):
        src = (EX / "reach_softflicker.vela").read_text(encoding="utf-8")
        text = emit_rust(parse(src, "reach_softflicker.vela"))
        self.assertIn('posture: "review"', text)
        self.assertIn("observe_only: false", text)
        self.assertIn("soft_flicker: true", text)

    def test_emit_refuses_closed_write_under_observe(self):
        src = """
lang vela 0.1
controller Sneak {
  posture observe
  compose Detect + SoftReprobe + QuietReach
  signals:
    epoch: Epoch
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
"""
        prog = parse(src, "sneak.vela")
        with self.assertRaises(EmitRustError) as cm:
            emit_rust(prog)
        self.assertIn("QuietReach", str(cm.exception))
        self.assertIn("refuse", str(cm.exception).lower())

    def test_cli_check_compile_digest_reach(self):
        reach = str(EX / "reach.vela")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", reach])
        self.assertEqual(rc, 0, buf.getvalue())
        out = buf.getvalue()
        self.assertIn("observe-only", out)
        self.assertIn("passthrough", out)
        self.assertIn("0.58", out)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["digest", reach])
        self.assertEqual(rc, 0, buf.getvalue())
        dig = buf.getvalue()
        self.assertIn("observe-only", dig)
        self.assertIn("passthrough", dig)
        self.assertIn("typed_reconfig", dig)
        self.assertIn("typed_loss", dig)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["compile", reach, "-o", "/tmp/vela-reach-cca-test.py"])
        self.assertEqual(rc, 0, buf.getvalue())


if __name__ == "__main__":
    unittest.main()
