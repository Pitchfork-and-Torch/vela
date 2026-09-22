"""Hint role + age rail: mismatch and stale fail closed (hints can lie)."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    check,
    hint_role_mismatch_error,
    hint_stale_age_error,
)
from vela.cli import main as vela_main
from vela.oracle import (
    hint_age_ok,
    hint_role_age_accept,
    hint_role_ok,
)
from vela.parser import parse
from vela.types import HINT_TRUSTED_ROLES, HOUSE_HINT_MAX_AGE_S

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(body: str) -> str:
    return f"""
lang vela 0.1
use std.hint
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


class TestHintRoleAgeConstants(unittest.TestCase):
    def test_trusted_roles_match_ascent_ingest(self):
        self.assertEqual(HINT_TRUSTED_ROLES, frozenset({"pilot", "gateway"}))

    def test_house_max_age_positive(self):
        self.assertGreater(HOUSE_HINT_MAX_AGE_S, 0.0)
        self.assertEqual(HOUSE_HINT_MAX_AGE_S, 2.0)


class TestHintRoleAgeRuntime(unittest.TestCase):
    def test_role_ok(self):
        self.assertTrue(hint_role_ok("pilot"))
        self.assertTrue(hint_role_ok("gateway"))
        self.assertTrue(hint_role_ok("Pilot"))
        self.assertFalse(hint_role_ok("untrusted"))
        self.assertFalse(hint_role_ok("sim"))
        self.assertFalse(hint_role_ok(None))
        self.assertFalse(hint_role_ok(""))

    def test_age_ok(self):
        self.assertTrue(hint_age_ok(0.0))
        self.assertTrue(hint_age_ok(1.999))
        self.assertFalse(hint_age_ok(2.0))
        self.assertFalse(hint_age_ok(2.5))
        self.assertFalse(hint_age_ok(None))
        self.assertFalse(hint_age_ok(-0.1))

    def test_accept_fail_closed(self):
        self.assertTrue(hint_role_age_accept("pilot", 1.0))
        self.assertTrue(hint_role_age_accept("gateway", 0.5))
        self.assertFalse(hint_role_age_accept("untrusted", 0.1))
        self.assertFalse(hint_role_age_accept("pilot", 2.5))
        self.assertFalse(hint_role_age_accept(None, 0.1))
        self.assertFalse(hint_role_age_accept("pilot", None))


class TestHintRoleAgeCheck(unittest.TestCase):
    def test_ascent_stamps_rail(self):
        src = (EX / "ascent.vela").read_text(encoding="utf-8")
        res = check(parse(src, "ascent.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hint_fail_closed)
        self.assertTrue(res.hint_role_age)
        self.assertEqual(res.posture, "observe")

    def test_reach_does_not_require_hint_rail(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(res.hint_fail_closed)
        self.assertFalse(res.hint_role_age)
        self.assertTrue(res.observe_only)

    def test_trusted_role_match_ok(self):
        src = _src(
            """
  when hint.ascent {
    require hint.ascent.role == "pilot" then freeze min_rtt, bw
  }
"""
        )
        res = check(parse(src, "role-ok.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.hint_role_age)

    def test_gateway_role_ok(self):
        src = _src(
            """
  when hint.ascent {
    require hint.ascent.role == "gateway" then freeze min_rtt, bw
  }
"""
        )
        res = check(parse(src, "role-gw.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_untrusted_role_mismatch(self):
        src = _src(
            """
  when hint.ascent {
    require hint.ascent.role == "untrusted" then freeze min_rtt, bw
  }
"""
        )
        res = check(parse(src, "role-bad.vela"))
        self.assertFalse(res.ok)
        self.assertIn(hint_role_mismatch_error("Probe", "untrusted"), res.errors)

    def test_neq_trusted_is_mismatch(self):
        src = _src(
            """
  when hint.ascent {
    require hint.ascent.role != "pilot" then freeze min_rtt, bw
  }
"""
        )
        res = check(parse(src, "role-neq.vela"))
        self.assertFalse(res.ok)
        self.assertIn(hint_role_mismatch_error("Probe", "pilot"), res.errors)

    def test_stale_age_selector(self):
        src = _src(
            """
  when hint.ascent {
    require hint.ascent.age > 2s then freeze min_rtt, bw
  }
"""
        )
        res = check(parse(src, "stale.vela"))
        self.assertFalse(res.ok)
        self.assertIn(hint_stale_age_error("Probe"), res.errors)

    def test_fresh_age_ok(self):
        src = _src(
            """
  when hint.ascent {
    require hint.ascent.age < 2s then freeze min_rtt, bw
  }
"""
        )
        res = check(parse(src, "fresh.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_softreprobe_cut_unchanged(self):
        src = (EX / "ascent.vela").read_text(encoding="utf-8")
        self.assertIn("cut: 0.58", src)
        src_r = (EX / "reach.vela").read_text(encoding="utf-8")
        self.assertIn("0.58", src_r)


class TestHintRoleAgeCli(unittest.TestCase):
    def test_ascent_cli_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "ascent.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("hint=fail-closed", out)
        self.assertIn("hint-role+age", out)
        self.assertIn("0.58", out)

    def test_reach_cli_no_leo_aware_and_no_hint_rail(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("observe-only", out)
        self.assertNotIn("hint-role+age", out)
        # check path must not pull leo-aware-transport
        import sys

        self.assertFalse(any("leo_cc" in m or "leo_aware" in m for m in sys.modules))


class TestHintRoleAgeDocs(unittest.TestCase):
    def test_language_names_rail(self):
        text = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("Role + age checks are the remaining rail", text)
        self.assertIn("mismatch or stale => None", text)
        self.assertIn("Hint role + age rail", text)

    def test_no_dish_mbps_claim(self):
        text = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        # law text must not invent dish throughput claims
        self.assertNotIn("dish Mbps", text.lower().replace("not dish", "NOTDISH"))


class TestHintRoleAgeKernelGate(unittest.TestCase):
    def test_on_path_hint_drops_bad_role(self):
        from vela.kernel import HorizonCCA
        from vela.ir import VelaConfig

        class FakeLeo:
            def __init__(self):
                self.calls = []

            def on_path_hint(self, t, reconfigured, **kw):
                self.calls.append((t, reconfigured, kw))

        cca = HorizonCCA.__new__(HorizonCCA)
        cca.cfg = VelaConfig()
        cca._leo = FakeLeo()
        # bad role: drop
        HorizonCCA.on_path_hint(cca, 1.0, False, role="untrusted", age_s=0.1, capacity_bps=1e7)
        self.assertEqual(cca._leo.calls, [])
        # stale age: drop
        HorizonCCA.on_path_hint(cca, 1.0, False, role="pilot", age_s=9.0, capacity_bps=1e7)
        self.assertEqual(cca._leo.calls, [])
        # good: forward (no next_capacity)
        HorizonCCA.on_path_hint(cca, 1.0, True, role="pilot", age_s=0.5, capacity_bps=1e7)
        self.assertEqual(len(cca._leo.calls), 1)
        self.assertEqual(cca._leo.calls[0][2].get("capacity_bps"), 1e7)
        self.assertNotIn("role", cca._leo.calls[0][2])
        # no role/age kwargs: passthrough (endpoint-only)
        HorizonCCA.on_path_hint(cca, 2.0, False, capacity_bps=2e7)
        self.assertEqual(len(cca._leo.calls), 2)


if __name__ == "__main__":
    unittest.main()
