"""Public teaser must be observe-only Reach. Not a closed-write intro."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from vela.checker import check
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
LANGUAGE = ROOT / "docs" / "LANGUAGE.md"

VELA_FENCE = re.compile(r"```vela\n(.*?)```", re.DOTALL)
# Live cruise-write syntax. Prose may say "pace" or "chase".
CRUISE_WRITE = re.compile(r"(?:pace\s*=|chase\s+delivery)")
OLD_WHEN_PACE = "The body may `freeze`, scale `pace`"


def _vela_fences(text: str) -> list[str]:
    return [m.group(1) for m in VELA_FENCE.finditer(text)]


class TestTeaserSafety(unittest.TestCase):
    def test_readme_vela_fences_are_observe_passthrough(self):
        srcs = _vela_fences(README.read_text(encoding="utf-8"))
        self.assertTrue(srcs, "README must show a checkable .vela program")
        for i, src in enumerate(srcs):
            prog = parse(src, f"README.md#vela-{i}")
            res = check(prog)
            self.assertTrue(res.ok, (i, res.errors))
            self.assertEqual(res.posture, "observe", i)
            self.assertTrue(res.observe_only, i)
            self.assertTrue(res.passthrough, i)
            self.assertEqual(prog.controllers[0].name, "Reach", i)
            self.assertEqual(res.closed_writes, [])

    def test_readme_has_no_live_cruise_write(self):
        text = README.read_text(encoding="utf-8")
        hit = CRUISE_WRITE.search(text)
        self.assertIsNone(
            hit,
            "README teaser must not show a cruise write "
            f"(found {hit.group(0)!r})" if hit else "",
        )

    def test_language_when_body_does_not_invite_observe_pace(self):
        text = LANGUAGE.read_text(encoding="utf-8")
        self.assertNotIn(OLD_WHEN_PACE, text)
        self.assertIn("Under `posture observe` the body may `freeze` samples", text)
        self.assertIn("## D. Horizon (named compose on LeoAware, after OCE; not the current flagship)", text)
        self.assertIn("### D2. Flagship program: Reach (after Horizon and Luff)", text)


if __name__ == "__main__":
    unittest.main()
