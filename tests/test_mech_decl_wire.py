"""Optional LeoAware std.mech declaration wire.

Skips when the leo-aware-transport sibling is absent. Fail-closed paths are
unit-tested with an explicit missing root (no skip).
"""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.mech_decl import (
    GIFT_MECH_NAMES,
    HOUSE_ENDPOINT_CUT,
    LEOAWARE_MECH_SCHEMA,
    MechDeclError,
    cite_leoaware_surface,
    load_leoaware_decl,
    sibling_present,
    validate_against_leoaware,
    validate_stdlib_against_decl,
)
from vela.types import HOUSE_ENDPOINT_CUT as TYPES_CUT
from vela.types import LEOAWARE_MECH_SCHEMA as TYPES_SCHEMA
from vela.types import STDLIB_MECHANISMS


class TestMechDeclCite(unittest.TestCase):
    def test_schema_constant_matches_types(self) -> None:
        self.assertEqual(LEOAWARE_MECH_SCHEMA, TYPES_SCHEMA)
        self.assertEqual(LEOAWARE_MECH_SCHEMA, "leoaware.vela_std_mech/v1")
        self.assertEqual(HOUSE_ENDPOINT_CUT, TYPES_CUT)
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_local_cite_lists_gift_names(self) -> None:
        text = cite_leoaware_surface(None)
        self.assertIn(LEOAWARE_MECH_SCHEMA, text)
        self.assertIn("SoftReprobe", text)
        self.assertIn("0.58", text)
        self.assertIn("handover_flicker_hook", text)

    def test_gift_names_subset_of_vela_stdlib(self) -> None:
        missing = sorted(GIFT_MECH_NAMES - set(STDLIB_MECHANISMS))
        self.assertEqual(missing, [], msg=f"VELA stdlib missing gift names: {missing}")

    def test_fail_closed_when_sibling_missing(self) -> None:
        missing = Path("/tmp/vela-mech-decl-wire-no-sibling")
        report = validate_against_leoaware(root=missing, require_sibling=True)
        self.assertFalse(report.sibling_present)
        self.assertFalse(report.ok)
        self.assertTrue(report.errors)
        with self.assertRaises(MechDeclError):
            load_leoaware_decl(root=missing, require=True)
        self.assertEqual(load_leoaware_decl(root=missing, require=False), {})


@unittest.skipUnless(sibling_present(), "leo-aware-transport sibling absent")
class TestMechDeclAgainstSibling(unittest.TestCase):
    def test_validate_aligns_shared_surface(self) -> None:
        report = validate_against_leoaware(require_sibling=True)
        self.assertTrue(report.sibling_present)
        self.assertTrue(report.ok, msg=report.errors)
        self.assertEqual(report.schema, LEOAWARE_MECH_SCHEMA)
        self.assertEqual(report.endpoint_cut, 0.58)
        for name in (
            "Detect",
            "SoftReprobe",
            "OCE",
            "DualGateGuard",
            "SoftFlicker",
            "TypedLoss",
        ):
            self.assertIn(name, report.shared)

    def test_softreprobe_cut_not_retuned(self) -> None:
        decl = load_leoaware_decl(require=True)
        soft = decl["std_mech"]["SoftReprobe"]
        self.assertEqual(float(soft["leoaware"]["house_endpoint_cut"]), 0.58)
        self.assertEqual(float(decl["house"]["endpoint_cut"]), 0.58)

    def test_observe_handover_flicker_hook_present(self) -> None:
        decl = load_leoaware_decl(require=True)
        hooks = set(decl["observe_hooks"])
        self.assertIn("handover_flicker_hook", hooks)
        self.assertIn("classify_handover_flicker", hooks)

    def test_reach_flagship_observe_only(self) -> None:
        decl = load_leoaware_decl(require=True)
        reach = decl["gift_compose"]["Reach_flagship"]
        self.assertEqual(reach["posture"], "observe")
        self.assertEqual(set(reach["compose"]), {"Detect", "SoftReprobe"})

    def test_validate_stdlib_helper(self) -> None:
        decl = load_leoaware_decl(require=True)
        report = validate_stdlib_against_decl(decl)
        self.assertTrue(report.ok, msg=report.errors)


if __name__ == "__main__":
    unittest.main()
