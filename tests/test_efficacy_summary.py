"""CLI eval summary prints dead_seconds, flicker_dead_ms, and eval_law together."""
from __future__ import annotations

import json
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from vela.efficacy_summary import attach_efficacy, efficacy_view, format_efficacy_cli
from vela.eval_harness import _summarize
from vela.ir import VelaConfig
from vela.types import HOUSE_ENDPOINT_CUT


def _stamped() -> dict:
    return {
        "verdict": "INCOMPLETE",
        "power": "low",
        "gate": "fast",
        "honesty": "Means only. Do not mix OPE-fair v3.7 with coupled-rng.",
        "tables": [{"goodput_mean": 73.57, "goodput_mbps": 73.57}],
        "eval_law": "coupled-rng-v3.4-p95",
        "dead_seconds": {
            "metric": "dead_seconds_after_handover",
            "dead_s_mean": 1.25,
            "dead_s_median": 1.1,
            "recover_frac": 0.80,
        },
        "flicker_dead_ms": {
            "metric": "flicker_dead_ms",
            "flicker_dead_ms_mean": 400.0,
            "flicker_dead_ms_p95": 800.0,
            "recover_frac": 0.80,
        },
    }


class EfficacySummaryTest(unittest.TestCase):
    def test_cut_is_house_soft_reprobe(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)
        view = efficacy_view({})
        self.assertEqual(view["soft_reprobe_cut"], 0.58)

    def test_missing_arms_print_together_as_not_stamped(self):
        line = format_efficacy_cli({})
        self.assertEqual(line.count("\n"), 0)
        self.assertLess(line.index("eval_law="), line.index("dead_seconds"))
        self.assertLess(line.index("dead_seconds"), line.index("flicker_dead_ms"))
        self.assertIn("eval_law=not-stamped", line)
        self.assertIn("dead_seconds=not-stamped (RttHop)", line)
        self.assertIn("flicker_dead_ms=not-stamped (Flicker; not RttHop)", line)
        self.assertIn("cut=0.58", line)
        self.assertNotIn("Mbps", line)
        self.assertNotIn("73.57", line)
        self.assertNotIn("58.78", line)

    def test_stamped_arms_print_on_one_line(self):
        line = format_efficacy_cli(_stamped())
        self.assertIn("eval_law=coupled-rng-v3.4-p95", line)
        self.assertIn("dead_seconds mean=1.250000 median=1.100000 (RttHop)", line)
        self.assertIn("flicker_dead_ms mean=400.000 p95=800.000 (Flicker; not RttHop)", line)
        self.assertNotIn("Mbps", line)
        self.assertNotIn("73.57", line)
        self.assertNotIn("p95=1.100000", line)

    def test_empty_block_is_stamped_without_a_fake_mean(self):
        line = format_efficacy_cli({"dead_seconds": {}, "flicker_dead_ms": {"status": "not-stamped"}})
        self.assertIn("dead_seconds mean=n/a (RttHop)", line)
        self.assertIn("flicker_dead_ms=not-stamped (Flicker; not RttHop)", line)
        view = efficacy_view({"dead_seconds": {}})
        self.assertIsNone(view["dead_seconds"]["mean"])
        self.assertEqual(view["dead_seconds"]["status"], "stamped")

    def test_mixed_eval_law_field_does_not_join_eras(self):
        line = format_efficacy_cli(
            {"eval_law": "ope-fair-v3.7 + coupled-rng-v3.4-p95"}
        )
        self.assertIn("eval_law=mixed", line)
        self.assertNotIn("ope-fair", line)
        self.assertNotIn("coupled-rng", line)

    def test_dish_token_in_eval_law_is_not_printed(self):
        line = format_efficacy_cli({"eval_law": "dish 150 Mbps"})
        self.assertIn("eval_law=not-stamped", line)
        self.assertNotIn("Mbps", line)
        self.assertNotIn("150", line)

    def test_attach_ignores_a_poisoned_efficacy_object(self):
        summary = _stamped()
        summary["efficacy"] = {"eval_law": "dish 150 Mbps", "dead_seconds": {"mean": 9}}
        attach_efficacy(summary)
        again = efficacy_view(summary)
        self.assertEqual(summary["efficacy"], again)
        self.assertEqual(summary["efficacy"]["eval_law"], "coupled-rng-v3.4-p95")
        self.assertEqual(summary["efficacy"]["dead_seconds"]["mean"], 1.25)
        self.assertEqual(summary["dead_seconds"]["dead_s_mean"], 1.25)

    def test_summarize_goodput_does_not_leak_into_the_line(self):
        rows = []
        for seed in (13, 7):
            rows.append(
                {
                    "scenario": "leo_fast_ho",
                    "seed": seed,
                    "cca": "Reach",
                    "goodput_mbps": 73.57,
                    "p95_rtt_ms": 138.37,
                }
            )
        summary = _summarize(rows, VelaConfig(name="Reach", seeds=[13, 7]), duration_s=45)
        line = format_efficacy_cli(summary)
        self.assertIn("eval_law=not-stamped", line)
        self.assertIn("dead_seconds=not-stamped", line)
        self.assertIn("flicker_dead_ms=not-stamped", line)
        self.assertNotIn("73.57", line)
        self.assertNotIn("138.37", line)
        self.assertNotIn("Mbps", line)
        self.assertIn("OPE-fair", summary["honesty"])

    def test_cli_eval_prints_one_joined_line(self):
        summary = _stamped()
        summary["rows"] = []
        buf = StringIO()
        with (
            patch("vela.eval_harness.evaluate", return_value=summary),
            patch("vela.eval_harness.write_result", return_value=Path("results/eval_efficacy.json")),
            patch("vela.receipt.write_receipt", return_value=Path("results/receipt_efficacy.json")),
            patch("sys.stdout", buf),
        ):
            from vela.cli import main

            rc = main(["eval", "examples/reach.vela", "--fast", "--tag", "efficacy-join"])
        text = buf.getvalue()
        self.assertEqual(rc, 3)
        lines = text.splitlines()
        joined = [ln for ln in lines if ln.startswith("efficacy ")]
        self.assertEqual(len(joined), 1)
        self.assertIn("eval_law=coupled-rng-v3.4-p95", joined[0])
        self.assertIn("dead_seconds mean=1.250000", joined[0])
        self.assertIn("flicker_dead_ms mean=400.000 p95=800.000", joined[0])
        self.assertIn("cut=0.58", joined[0])
        start = lines.index("{")
        end = max(i for i, ln in enumerate(lines) if ln == "}")
        dumped = json.loads("\n".join(lines[start : end + 1]))
        self.assertEqual(dumped["efficacy"]["eval_law"], "coupled-rng-v3.4-p95")
        self.assertEqual(dumped["efficacy"]["dead_seconds"]["arm"], "RttHop")
        self.assertEqual(dumped["efficacy"]["flicker_dead_ms"]["not_arm"], "RttHop")
        self.assertEqual(dumped["efficacy"]["soft_reprobe_cut"], 0.58)
        self.assertIn("efficacy", summary)


if __name__ == "__main__":
    unittest.main()
