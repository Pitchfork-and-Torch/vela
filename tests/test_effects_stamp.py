"""Monoidal mech effects= stamp on vela check (Detect|SoftReprobe|IntervalBw)."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from vela.checker import check
from vela.cli import main
from vela.parser import parse
from vela.types import (
    HOUSE_ENDPOINT_CUT,
    STDLIB_MECHANISMS,
    effects_stamp_line,
    monoidal_write_effects,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


class TestMonoidalEffectsHelpers(unittest.TestCase):
    def test_house_cut_unchanged(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_reach_compose_write_union(self):
        names = [
            "Detect",
            "SoftReprobe",
            "Calendar",
            "IntervalBw",
            "WriteBudget",
            "DualGateGuard",
        ]
        writes, errs = monoidal_write_effects(names)
        self.assertEqual(errs, [])
        self.assertEqual(
            writes,
            [
                "budget",
                "bw",
                "chase_gain",
                "cwnd",
                "epoch",
                "min_rtt",
                "p_ho",
                "reconfig",
            ],
        )
        self.assertEqual(
            effects_stamp_line(writes),
            "budget|bw|chase_gain|cwnd|epoch|min_rtt|p_ho|reconfig",
        )

    def test_detect_softreprobe_intervalbw_only(self):
        writes, errs = monoidal_write_effects(
            ["Detect", "SoftReprobe", "IntervalBw"]
        )
        self.assertEqual(errs, [])
        self.assertEqual(
            writes,
            ["bw", "cwnd", "epoch", "min_rtt", "reconfig"],
        )

    def test_unknown_name_ignored_here(self):
        writes, errs = monoidal_write_effects(["Detect", "NotAMech"])
        self.assertEqual(errs, [])
        self.assertEqual(writes, ["reconfig"])

    def test_undeclared_schema_fails_closed(self):
        broken = dict(STDLIB_MECHANISMS["Detect"])
        del broken["writes"]
        with mock.patch.dict(STDLIB_MECHANISMS, {"Detect": broken}):
            writes, errs = monoidal_write_effects(["Detect"])
        self.assertTrue(any("undeclared effects" in e for e in errs))
        self.assertTrue(any("missing writes" in e for e in errs))


class TestEffectsStampCheck(unittest.TestCase):
    def test_reach_stamps_effects(self):
        res = check(
            parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(
            res.effects,
            "budget|bw|chase_gain|cwnd|epoch|min_rtt|p_ho|reconfig",
        )
        self.assertTrue(res.observe_only)
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_equinox_stamps_effects(self):
        res = check(
            parse(
                (EX / "equinox.vela").read_text(encoding="utf-8"), "equinox.vela"
            )
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.effects)
        self.assertIn("bw", res.effects.split("|"))
        self.assertIn("reconfig", res.effects.split("|"))

    def test_horizon_stamps_effects(self):
        res = check(
            parse(
                (EX / "horizon.vela").read_text(encoding="utf-8"), "horizon.vela"
            )
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.effects)
        self.assertIn("cwnd", res.effects.split("|"))

    def test_cli_reach_prints_effects(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["check", str(EX / "reach.vela")])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn(
            "effects=budget|bw|chase_gain|cwnd|epoch|min_rtt|p_ho|reconfig",
            out,
        )
        self.assertIn("monoid writes", out)
        self.assertIn("undeclared fails closed", out)
        self.assertIn("observe-only", out)

    def test_cli_equinox_prints_effects(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["check", str(EX / "equinox.vela")])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("effects=", out)
        self.assertIn("monoid writes", out)


class TestEffectsStampDocs(unittest.TestCase):
    def test_language_docs_effects_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("effects=", lang)
        self.assertIn("monoid", lang.lower())
        self.assertIn("undeclared", lang)
        self.assertIn("0.58", lang)
        self.assertIn("Detect + SoftReprobe + IntervalBw", lang)

    def test_equinox_docs_effects_stamp(self):
        eq = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("effects=", eq)
        self.assertIn("0.58", eq)


if __name__ == "__main__":
    unittest.main()
