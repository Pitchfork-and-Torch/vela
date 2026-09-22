"""LANGUAGE.md documents path flicker vs hop."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestLanguagePathFlickerDoc(unittest.TestCase):
    def test_language_names_flicker_not_hop(self):
        text = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("flicker ~ every", text)
        self.assertIn("RttHop", text)
        self.assertIn("SoftReprobe cut", text)
        self.assertIn("starlink_flicker.vela", text)
        self.assertIn("jitter must be", text.lower())
        self.assertIn("not the house gate", text)


if __name__ == "__main__":
    unittest.main()
