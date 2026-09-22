"""p-value and bootstrap badges fail closed. CI stays mean+/-std."""
from __future__ import annotations

import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from vela.checker import check
from vela.parser import parse
from vela.receipt import build_receipt, verify_receipt
from vela.stats_honesty import STATS_METHOD, summary_claims_badge
from vela.types import HOUSE_ENDPOINT_CUT

EX = Path(__file__).resolve().parents[1] / "examples"


def _prog(report: str, *, extra_assert: str = "", seeds: str = "13, 7, 42, 99, 123") -> str:
    asserts = "  assert terrestrial.goodput >= 77 Mbps\n"
    if extra_assert:
        asserts += f"  {extra_assert}\n"
    return f"""
lang vela 0.1
controller Probe {{
  compose Detect
}}
contract DualGate vs BBRv3approx {{
  seeds = [{seeds}]
  scenario leo_fast_ho duration 90s
  scenario terrestrial duration 40s
{asserts}  report {report}
}}
"""


class StatsHonestyTest(unittest.TestCase):
    def test_house_cut_stays(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_reach_stamps_mean_pm_std(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.stats, STATS_METHOD)
        buf = StringIO()
        with patch("sys.stdout", buf):
            from vela.cli import main

            rc = main(["check", str(EX / "reach.vela")])
        self.assertEqual(rc, 0)
        line = next(ln for ln in buf.getvalue().splitlines() if "stats=" in ln)
        self.assertIn("stats=mean+/-std", line)
        self.assertIn("no p-value", line)
        self.assertIn("no bootstrap", line)
        self.assertNotIn("Mbps", line)

    def test_p95_assert_is_not_a_p_value(self):
        src = _prog("ci(0.95)", extra_assert="assert mean(p95) <= baseline.p95")
        res = check(parse(src, "p95.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.stats, STATS_METHOD)

    def test_report_bootstrap_is_an_error(self):
        res = check(parse(_prog("ci(0.95), bootstrap"), "boot.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("bootstrap" in e and "refused" in e for e in res.errors), res.errors)
        self.assertEqual(res.stats, "")

    def test_report_p_is_an_error(self):
        res = check(parse(_prog("p(0.05)"), "pval.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("p(0.05)" in e for e in res.errors), res.errors)

    def test_assert_p_is_an_error(self):
        src = _prog("ci(0.95)", extra_assert="assert p < 0.05")
        res = check(parse(src, "assert-p.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("assert" not in e and "p" in e and "refused" in e for e in res.errors) or any(
            "badge 'p'" in e for e in res.errors
        ), res.errors)

    def test_eight_seeds_still_refuse_bootstrap(self):
        src = _prog(
            "bootstrap",
            seeds="13, 7, 42, 99, 123, 1, 2, 3",
        )
        res = check(parse(src, "n8.vela"))
        self.assertFalse(res.ok)
        self.assertEqual(res.power, "ok")
        self.assertTrue(any("bootstrap" in e for e in res.errors), res.errors)

    def test_receipt_refuses_a_smuggled_p_value(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        summary = {
            "verdict": "INCOMPLETE",
            "power": "low",
            "gate": "fast",
            "honesty": "Means only. p-values are not claimed.",
            "rows": [],
            "config": {"seeds": [13, 7], "duration_s": 45.0, "scenarios": ["leo_fast_ho", "terrestrial"]},
            "ci": {"method": "mean+/-std", "level": 0.95},
        }
        self.assertFalse(summary_claims_badge(summary))
        rec = build_receipt(
            source=src,
            source_name="reach.vela",
            compose=["Detect", "SoftReprobe"],
            config=summary["config"],
            summary=summary,
        )
        self.assertEqual(rec["stats_method"], "mean+/-std")
        self.assertEqual(rec["p_value"], "refused")
        self.assertEqual(verify_receipt(rec, source=src, summary=summary), [])
        poisoned = dict(summary)
        poisoned["p_value"] = 0.03
        self.assertTrue(summary_claims_badge(poisoned))
        errs = verify_receipt(rec, source=src, summary=poisoned)
        self.assertTrue(any("p-value" in e or "bootstrap" in e for e in errs), errs)
        self.assertNotIn("Mbps", rec["stats_method"])

    def test_receipt_rejects_a_bootstrap_method_field(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        summary = {
            "verdict": "INCOMPLETE",
            "power": "low",
            "gate": "fast",
            "honesty": "test",
            "rows": [],
            "config": {"seeds": [13, 7], "duration_s": 45.0, "scenarios": ["leo_fast_ho", "terrestrial"]},
        }
        rec = build_receipt(
            source=src,
            source_name="reach.vela",
            compose=["Detect"],
            config=summary["config"],
            summary=summary,
        )
        rec["stats_method"] = "bootstrap"
        rec.pop("receipt_digest")
        errs = verify_receipt(rec, summary=summary)
        self.assertTrue(any("stats_method" in e or "receipt_digest" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
