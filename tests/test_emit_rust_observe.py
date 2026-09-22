"""emit_rust / IR honesty for observe-only Reach."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.emit_rust import emit_rust
from vela.parser import parse


ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


class TestEmitRustObserve(unittest.TestCase):
    def test_reach_emit_stamps_observe_only(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        text = emit_rust(parse(src, "reach.vela"))
        self.assertIn("observe_only: true", text)
        self.assertIn('posture: "observe"', text)
        self.assertIn("passthrough: true", text)
        self.assertIn("horizon_chase: false", text)
        self.assertIn("soft_flicker: false", text)
        self.assertIn("quiet_reach: false", text)
        self.assertIn("Mech enum is a catalog", text)
        self.assertIn("Do not claim a dual-gate win", text)
        # Closed-write names may appear in the catalog enum, but Reach
        # compose must not list them as enabled mechs.
        self.assertIn("Mech::Detect", text)
        self.assertIn("Mech::SoftReprobe", text)
        self.assertNotIn("Mech::HorizonChase", text.split("mechs: &[")[1].split("]")[0])
        self.assertNotIn("Mech::SoftFlicker", text.split("mechs: &[")[1].split("]")[0])

    def test_equinox_emit_is_observe_only(self):
        src = (EX / "equinox.vela").read_text(encoding="utf-8")
        text = emit_rust(parse(src, "equinox.vela"))
        self.assertIn("observe_only: true", text)
        self.assertIn('posture: "observe"', text)

    def test_review_softflicker_emit_does_not_pretend_observe(self):
        src = (EX / "reach_softflicker.vela").read_text(encoding="utf-8")
        text = emit_rust(parse(src, "reach_softflicker.vela"))
        # Review compose may enable SoftFlicker; must not stamp observe_only.
        self.assertIn('posture: "review"', text)
        self.assertIn("observe_only: false", text)
        self.assertIn("soft_flicker: true", text)


if __name__ == "__main__":
    unittest.main()
