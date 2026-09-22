"""Hint ingress: stale / role-mismatched ASCENT-D/Orb stays None.

Bare hint.ascent arithmetic remains illegal (checker). Flagship Reach
stays defined without hints. Ingress is fail-closed, not a hop oracle.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check, hint_law_error
from vela.hint import (
    DEFAULT_MAX_AGE_S,
    HINT_ROLES,
    PathHint,
    admit_hint,
)
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


class TestHintIngressFailClosed(unittest.TestCase):
    def test_admit_fresh_ascent_d(self):
        h = admit_hint(
            present=True,
            role="ascent-d",
            expected_role="ascent-d",
            age_s=0.4,
            channel="ascent",
        )
        self.assertIsInstance(h, PathHint)
        self.assertEqual(h.role, "ascent-d")
        self.assertEqual(h.channel, "ascent")

    def test_missing_is_none(self):
        self.assertIsNone(
            admit_hint(
                present=False,
                role="ascent-d",
                expected_role="ascent-d",
                age_s=0.1,
            )
        )

    def test_integrity_fail_erases(self):
        self.assertIsNone(
            admit_hint(
                present=True,
                role="ascent-d",
                expected_role="ascent-d",
                age_s=0.1,
                integrity_ok=False,
            )
        )

    def test_role_mismatch_erases(self):
        self.assertIsNone(
            admit_hint(
                present=True,
                role="orb",
                expected_role="ascent-d",
                age_s=0.1,
                channel="ascent",
            )
        )

    def test_unknown_role_erases(self):
        self.assertIsNone(
            admit_hint(
                present=True,
                role="not-a-role",
                expected_role="ascent-d",
                age_s=0.1,
            )
        )
        self.assertIn("ascent-d", HINT_ROLES)

    def test_stale_age_erases(self):
        self.assertIsNone(
            admit_hint(
                present=True,
                role="ascent-d",
                expected_role="ascent-d",
                age_s=DEFAULT_MAX_AGE_S + 0.01,
            )
        )

    def test_age_at_ceiling_ok(self):
        h = admit_hint(
            present=True,
            role="orb",
            expected_role="orb",
            age_s=DEFAULT_MAX_AGE_S,
            channel="orb",
        )
        self.assertIsNotNone(h)

    def test_negative_age_erases(self):
        self.assertIsNone(
            admit_hint(
                present=True,
                role="ascent-d",
                expected_role="ascent-d",
                age_s=-0.01,
            )
        )

    def test_unknown_channel_erases(self):
        self.assertIsNone(
            admit_hint(
                present=True,
                role="ascent-d",
                expected_role="ascent-d",
                age_s=0.1,
                channel="next_capacity",
            )
        )

    def test_reach_still_defined_without_hints(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.hint_fail_closed)

    def test_ascent_still_fail_closed_surface(self):
        src = (EX / "ascent.vela").read_text(encoding="utf-8")
        res = check(parse(src, "ascent.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hint_fail_closed)

    def test_bare_hint_ascent_still_illegal(self):
        src = """
lang vela 0.1
use std.hint
use std.path
controller Probe {
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    hint: Hint<PathHint>
  on Reconfig(e) match e {
    RttHop => hold
    Flicker => hold
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => hold
    Unknown => hold
  }
  every ack {
    let x = hint.ascent
  }
}
path LeoFastHO {
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
"""
        res = check(parse(src, "bare-hint.vela"))
        self.assertFalse(res.ok)
        self.assertIn(hint_law_error("Probe", "hint"), res.errors)


if __name__ == "__main__":
    unittest.main()
