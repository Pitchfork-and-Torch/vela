"""One efficacy CLI line: eval_law + hop dead_seconds + flicker_dead_ms + power."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from vela.eval_summary import (
    FLICKER_LABEL,
    HOP_LABEL,
    SOFT_REPROBE_CUT,
    format_efficacy_summary_line,
    merge_efficacy_payload,
    print_efficacy_summary,
)


class EvalSummaryLineTests(unittest.TestCase):
    def test_empty_payload_is_blank(self):
        self.assertEqual(format_efficacy_summary_line({}), "")
        self.assertEqual(format_efficacy_summary_line(None), "")

    def test_power_only(self):
        line = format_efficacy_summary_line({"power": "low"})
        self.assertIn("efficacy  ", line)
        self.assertIn("power=low", line)
        self.assertIn(f"SoftReprobe={SOFT_REPROBE_CUT}", line)
        self.assertNotIn("eval_law=", line)
        self.assertNotIn("dead_seconds", line)
        self.assertNotIn("flicker_dead_ms", line)

    def test_all_four_fields_one_line(self):
        summary = {
            "eval_law": "coupled-rng-v3.4-p95",
            "dead_seconds": {
                "metric": "dead_seconds_after_handover",
                "dead_s_mean": 1.2,
                "dead_s_median": 1.1,
                "dead_s_p95": 2.0,
            },
            "flicker_dead_ms": {
                "metric": "flicker_dead_ms",
                "flicker_dead_ms_mean": 800.0,
                "flicker_dead_ms_p95": 900.0,
            },
            "power": "low",
        }
        line = format_efficacy_summary_line(summary)
        self.assertTrue(line.startswith("efficacy  "))
        self.assertIn("eval_law=coupled-rng-v3.4-p95", line)
        self.assertIn("dead_seconds mean=1.200000 p95=2.000000", line)
        self.assertIn(f"({HOP_LABEL})", line)
        self.assertIn("flicker_dead_ms mean=800.000 p95=900.000", line)
        self.assertIn(f"({FLICKER_LABEL})", line)
        self.assertIn("power=low", line)
        self.assertIn(f"SoftReprobe={SOFT_REPROBE_CUT}", line)
        # One surface: a single line, not four separate prints.
        self.assertEqual(line.count("\n"), 0)

    def test_hop_block_falls_back_to_median(self):
        # #46 stamps median; #53 CLI prefers p95 when present.
        line = format_efficacy_summary_line(
            {
                "dead_seconds": {
                    "metric": "dead_seconds_after_handover",
                    "dead_s_mean": 0.5,
                    "dead_s_median": 0.4,
                }
            }
        )
        self.assertIn("dead_seconds mean=0.500000 p95=0.400000", line)
        self.assertIn(HOP_LABEL, line)

    def test_receipt_and_summary_merge_summary_wins(self):
        receipt = {"power": "ok", "eval_law": "from-receipt"}
        summary = {"power": "low", "eval_law": "from-summary"}
        merged = merge_efficacy_payload(summary, receipt)
        self.assertEqual(merged["power"], "low")
        self.assertEqual(merged["eval_law"], "from-summary")
        line = format_efficacy_summary_line(summary, receipt=receipt)
        self.assertIn("eval_law=from-summary", line)
        self.assertIn("power=low", line)

    def test_receipt_only_power(self):
        line = format_efficacy_summary_line(None, receipt={"power": "ok"})
        self.assertIn("power=ok", line)

    def test_print_efficacy_summary_emits_line(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            out = print_efficacy_summary({"power": "low", "eval_law": "coupled-rng-v3.4-p95"})
        text = buf.getvalue()
        self.assertEqual(out, text.strip())
        self.assertIn("efficacy  ", text)
        self.assertIn("eval_law=coupled-rng-v3.4-p95", text)
        self.assertIn("power=low", text)

    def test_print_blank_when_empty(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            out = print_efficacy_summary({})
        self.assertEqual(out, "")
        self.assertEqual(buf.getvalue(), "")

    def test_soft_reprobe_cut_is_house_058(self):
        self.assertEqual(SOFT_REPROBE_CUT, 0.58)


if __name__ == "__main__":
    unittest.main()
