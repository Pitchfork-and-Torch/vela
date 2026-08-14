"""Hint law: fail-closed Option. Missing is not a hop oracle."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check, hint_law_error
from vela.compile import compile_source
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(uses: str, body: str) -> str:
    return f"""
lang vela 0.1
{uses}
controller Probe {{
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    hint: Hint<PathHint>
{body}
{LOSS}
}}
"""


class TestHintLaw(unittest.TestCase):
    def test_ascent_example_checks(self):
        src = (EX / "ascent.vela").read_text(encoding="utf-8")
        prog = parse(src, "ascent.vela")
        self.assertIn("std.hint", prog.uses)
        self.assertEqual(prog.controllers[0].name, "Ascent")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hint_fail_closed)
        self.assertEqual(res.posture, "observe")
        self.assertTrue(res.observe_only)
        self.assertTrue(res.typed_reconfig)
        self.assertEqual(res.closed_writes, [])
        self.assertEqual(prog.controllers[0].posture, "observe")
        self.assertEqual(
            prog.controllers[0].compose,
            ["Detect", "SoftReprobe", "Calendar", "IntervalBw", "DualGateGuard"],
        )
        _, cfg = compile_source(src, "ascent.vela")
        self.assertEqual(cfg.name, "Ascent")
        self.assertTrue(cfg.observe_only)
        self.assertFalse(cfg.horizon_chase)
        self.assertFalse(cfg.quiet_reach)
        self.assertFalse(cfg.trim_hold)

    def test_reach_stays_defined_without_hints(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.hint_fail_closed)
        self.assertTrue(res.observe_only)
        self.assertTrue(res.typed_reconfig)
        self.assertEqual(res.posture, "observe")

    def test_bare_hint_as_point_is_error(self):
        src = _src(
            "use std.hint",
            """
  every ack {
    let x = hint.ascent
  }
""",
        )
        res = check(parse(src, "bare-hint.vela"))
        self.assertFalse(res.ok)
        self.assertIn(hint_law_error("Probe", "hint"), res.errors)

    def test_when_hint_ascent_proves_some(self):
        src = _src(
            "use std.hint",
            """
  when hint.ascent {
    freeze min_rtt, bw for 1.4 * rtt
  }
""",
        )
        res = check(parse(src, "when-hint.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_require_hint_then_freeze_ok(self):
        src = _src(
            "use std.hint",
            """
  every ack {
    require hint.ascent then freeze min_rtt, bw for 1.4 * rtt
  }
""",
        )
        res = check(parse(src, "require-hint.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_hint_age_without_proof_is_error(self):
        src = _src(
            "use std.hint",
            """
  when hint.ascent.age < 2s {
    freeze min_rtt, bw
  }
""",
        )
        res = check(parse(src, "age.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("hint law" in e for e in res.errors))

    def test_on_hint_must_match_some_none(self):
        src = _src(
            "use std.hint",
            """
  on Hint(h) {
    freeze min_rtt, bw
  }
""",
        )
        res = check(parse(src, "hint-bare.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("Some | None" in e for e in res.errors))

    def test_on_hint_match_missing_none(self):
        src = _src(
            "use std.hint",
            """
  on Hint(h) match h {
    Some => hold
  }
""",
        )
        res = check(parse(src, "hint-some.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("None" in e and "fail-closed" in e for e in res.errors))

    def test_on_hint_some_may_use_hint(self):
        src = _src(
            "use std.hint",
            """
  on Hint(h) match h {
    Some => {
      freeze min_rtt, bw for 1.4 * rtt
    }
    None => hold
  }
""",
        )
        res = check(parse(src, "hint-match.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_on_hint_none_cannot_act(self):
        src = _src(
            "use std.hint",
            """
  on Hint(h) match h {
    Some => hold
    None => {
      let x = hint.ascent
    }
  }
""",
        )
        res = check(parse(src, "hint-none.vela"))
        self.assertFalse(res.ok)
        self.assertIn(hint_law_error("Probe", "hint"), res.errors)

    def test_hint_requires_use_std_hint(self):
        src = _src(
            "",
            """
  on Hint(h) match h {
    Some => hold
    None => hold
  }
""",
        )
        res = check(parse(src, "no-use.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("use std.hint" in e for e in res.errors))

    def test_unknown_use_module_is_error(self):
        src = """
lang vela 0.1
use std.notamodule
controller Probe {
  compose Detect
}
"""
        res = check(parse(src, "bad-use.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("unknown module" in e for e in res.errors))

    def test_prior_min_rtt_write_is_error(self):
        src = """
lang vela 0.1
controller Probe {
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt
      min_rtt = prior.min_rtt
    }
    Flicker => hold
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "prior.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("prior.min_rtt" in e for e in res.errors))

    def test_existing_examples_still_check(self):
        for name in (
            "horizon.vela",
            "reach.vela",
            "luff.vela",
            "equinox.vela",
            "ascent.vela",
        ):
            src = (EX / name).read_text(encoding="utf-8")
            res = check(parse(src, name))
            self.assertTrue(res.ok, (name, res.errors))


if __name__ == "__main__":
    unittest.main()
