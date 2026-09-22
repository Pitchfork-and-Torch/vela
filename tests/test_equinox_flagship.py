"""Equinox / CONSTELLATION align with Reach observe-only flagship stamps."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check
from vela.parser import parse


ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"
HOUSE_CUT = "0.58"


def _flat(text: str) -> str:
    return " ".join(text.split())


class TestEquinoxFlagshipAlign(unittest.TestCase):
    def _check(self, name: str):
        src = (EX / name).read_text(encoding="utf-8")
        res = check(parse(src, name))
        self.assertTrue(res.ok, (name, res.errors))
        return src, res

    def test_equinox_stamps_match_reach_observe_laws(self):
        reach_src, reach = self._check("reach.vela")
        eq_src, equinox = self._check("equinox.vela")
        ascent_src, ascent = self._check("ascent.vela")

        for name, res in (
            ("reach.vela", reach),
            ("equinox.vela", equinox),
            ("ascent.vela", ascent),
        ):
            self.assertEqual(res.posture, "observe", name)
            self.assertTrue(res.observe_only, name)
            self.assertTrue(res.passthrough, name)
            self.assertTrue(res.typed_reconfig, name)
            self.assertTrue(res.typed_loss, name)
            self.assertEqual(res.closed_writes, [], name)
            self.assertIn(HOUSE_CUT, (EX / name).read_text(encoding="utf-8"), name)

        # Same LeoAware wrap compose class (Reach + Equinox).
        self.assertEqual(reach.compose_digest, equinox.compose_digest)
        self.assertIn("WriteBudget", reach.mechanisms)
        self.assertIn("SoftReprobe", equinox.mechanisms)
        self.assertNotIn("HorizonChase", equinox.mechanisms)
        self.assertNotIn("SoftFlicker", equinox.mechanisms)

        # Equinox refuse rail, not a write enable.
        self.assertEqual(equinox.writecap, "budget")
        self.assertEqual(equinox.authority.get("cwnd"), 0)
        self.assertIn("Observe", equinox.views)

        # Ascent is hint fail-closed on the same observe laws.
        self.assertTrue(ascent.hint_fail_closed)
        self.assertIn("0.58", ascent_src)
        self.assertIn("passthrough", eq_src)

    def test_docs_name_reach_flagship_not_closed_write_intro(self):
        equinox_doc = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        constel = (ROOT / "docs" / "CONSTELLATION.md").read_text(encoding="utf-8")
        language = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        src = (EX / "equinox.vela").read_text(encoding="utf-8")

        for text, label in (
            (equinox_doc, "EQUINOX.md"),
            (constel, "CONSTELLATION.md"),
            (src, "equinox.vela"),
            (agents, "AGENTS.md"),
        ):
            self.assertIn("reach.vela", text, label)
            self.assertIn("0.58", text, label)

        self.assertIn("Not a closed-write intro", equinox_doc)
        self.assertIn("passthrough", equinox_doc)
        self.assertIn("Flagship surface", equinox_doc)
        self.assertIn("Flagship surface", constel)
        self.assertIn("discipline demo", constel)
        self.assertIn("reach.vela", language)
        self.assertIn("not a closed-write intro", language.lower())
        self.assertIn("discipline demo", readme.lower())
        self.assertIn("Not a closed-write intro", src)
        self.assertIn("passthrough", src)
        self.assertNotIn("Equinox enables closed-write", equinox_doc)
        needle = "Do not merge a review closed-write compose as the flagship"
        self.assertIn(needle, _flat(equinox_doc), "EQUINOX.md")
        self.assertIn(needle, _flat(constel), "CONSTELLATION.md")


if __name__ == "__main__":
    unittest.main()
