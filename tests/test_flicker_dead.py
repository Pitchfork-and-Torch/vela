"""flicker_dead_ms: synthetic Flicker fixture + hop-coincide filter + labels."""
from __future__ import annotations

import unittest

from vela.eval_harness import _summarize, honesty_text
from vela.flicker_dead import (
    FLICKER_DEAD_RECOVER_FRAC,
    FLICKER_EVENT_KIND,
    FLICKER_NOT_HOP_LABEL,
    SOFT_REPROBE_CUT,
    compute_flicker_dead_ms,
    filter_flicker_times,
    flicker_dead_summary,
    format_flicker_dead_cli,
    row_flicker_dead_fields,
)
from vela.ir import VelaConfig


def _synthetic_flicker_series():
    """One Flicker at t=5. Pre-event median 100 Mbps. Dip then recover to 80%."""
    t = [i * 0.05 for i in range(0, 401)]  # 0..20
    flick_t = 5.0
    gps = []
    for tt in t:
        if tt < flick_t:
            gps.append(100e6)
        elif tt < flick_t + 0.8:
            gps.append(10e6)  # dead / collapsed
        else:
            gps.append(85e6)  # recovered above 80% of 100
    return t, gps, [flick_t]


class TestFlickerDeadSynthetic(unittest.TestCase):
    def test_recover_frac_default(self):
        self.assertEqual(FLICKER_DEAD_RECOVER_FRAC, 0.80)
        self.assertEqual(SOFT_REPROBE_CUT, 0.58)
        self.assertEqual(FLICKER_EVENT_KIND, "Flicker")

    def test_synthetic_recovers_at_800ms(self):
        t, gp, flicks = _synthetic_flicker_series()
        detail = compute_flicker_dead_ms(t, gp, flicks, end_t=20.0)
        self.assertEqual(detail["n_flickers"], 1)
        self.assertEqual(detail["n_censored"], 0)
        self.assertTrue(detail["not_rtt_hop"])
        self.assertEqual(detail["event_kind"], "Flicker")
        self.assertIn("not RttHop", detail["label"])
        ev = detail["events"][0]
        self.assertAlmostEqual(ev["flicker_t"], 5.0)
        self.assertAlmostEqual(ev["pre_event_median_bps"], 100e6)
        self.assertAlmostEqual(ev["threshold_bps"], 80e6)
        # first sample at/after 5.8s hits 85e6 -> 800 ms
        self.assertAlmostEqual(ev["flicker_dead_ms"], 800.0, places=1)
        self.assertFalse(ev["censored"])
        self.assertAlmostEqual(detail["flicker_dead_ms_mean"], 800.0, places=1)
        self.assertAlmostEqual(detail["flicker_dead_ms_p95"], 800.0, places=1)

    def test_drops_flicker_coincident_with_hop(self):
        kept = filter_flicker_times([10.0, 12.0], hop_times=[10.01, 20.0])
        self.assertEqual(kept, [12.0])

    def test_hop_coincide_not_counted_as_flicker(self):
        t = [i * 0.1 for i in range(0, 201)]
        gp = [100e6 if tt < 10 else (10e6 if tt < 11 else 90e6) for tt in t]
        # Flicker mark sits on the hop -> dropped; no Flicker events remain.
        detail = compute_flicker_dead_ms(
            t, gp, [10.0], hop_times=[10.0], end_t=20.0
        )
        self.assertEqual(detail["n_dropped_hop_coincide"], 1)
        self.assertEqual(detail["n_flickers"], 0)
        self.assertIsNone(detail["flicker_dead_ms_mean"])

    def test_censored_when_never_recovers(self):
        t = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        gp = [100e6, 100e6, 5e6, 5e6, 5e6, 5e6]
        detail = compute_flicker_dead_ms(t, gp, [2.0], end_t=5.0)
        self.assertEqual(detail["n_censored"], 1)
        self.assertTrue(detail["events"][0]["censored"])
        self.assertAlmostEqual(detail["events"][0]["flicker_dead_ms"], 3000.0)

    def test_p95_across_two_events(self):
        # Flicker at 5 -> 500ms dead; at 12 -> 1500ms dead.
        t = [i * 0.1 for i in range(0, 201)]  # 0..20
        gp = []
        for tt in t:
            if tt < 5.0:
                gp.append(100e6)
            elif tt < 5.5:
                gp.append(10e6)
            elif tt < 12.0:
                gp.append(100e6)
            elif tt < 13.5:
                gp.append(10e6)
            else:
                gp.append(100e6)
        detail = compute_flicker_dead_ms(t, gp, [5.0, 12.0], end_t=20.0)
        self.assertEqual(detail["n_flickers"], 2)
        self.assertAlmostEqual(detail["events"][0]["flicker_dead_ms"], 500.0, places=0)
        self.assertAlmostEqual(detail["events"][1]["flicker_dead_ms"], 1500.0, places=0)
        # nearest-rank p95 of [500, 1500] -> 1500
        self.assertAlmostEqual(detail["flicker_dead_ms_p95"], 1500.0, places=0)

    def test_row_and_summary_helpers(self):
        t, gp, flicks = _synthetic_flicker_series()
        detail = compute_flicker_dead_ms(t, gp, flicks)
        fields = row_flicker_dead_fields(detail)
        self.assertEqual(fields["flicker_dead_ms_n"], 1)
        self.assertEqual(fields["flicker_event_kind"], "Flicker")
        self.assertTrue(fields["flicker_not_rtt_hop"])
        self.assertAlmostEqual(fields["flicker_dead_ms_mean"], 800.0, places=1)
        agg = flicker_dead_summary(
            [
                {
                    "flicker_dead_ms_mean": 800.0,
                    "flicker_dead_ms_p95": 800.0,
                    "flicker_dead_ms_n": 1,
                    "flicker_dead_ms_n_censored": 0,
                    "flicker_dead_ms_recover_frac": 0.80,
                }
            ]
        )
        self.assertEqual(agg["recover_pct"], 80)
        self.assertEqual(agg["soft_reprobe_cut"], 0.58)
        self.assertTrue(agg["not_rtt_hop"])
        self.assertAlmostEqual(agg["flicker_dead_ms_mean"], 800.0, places=1)
        self.assertAlmostEqual(agg["flicker_dead_ms_p95"], 800.0, places=1)

    def test_cli_line_labels_not_hop(self):
        line = format_flicker_dead_cli(
            {
                "flicker_dead_ms_mean": 800.0,
                "flicker_dead_ms_p95": 900.0,
                "n_flickers_total": 2,
            }
        )
        self.assertIn("flicker_dead_ms", line)
        self.assertIn("mean=800.000", line)
        self.assertIn("p95=900.000", line)
        self.assertIn(FLICKER_NOT_HOP_LABEL, line)
        self.assertIn("0.58", line)


class TestFlickerDeadEvalStamp(unittest.TestCase):
    def test_summarize_stamps_flicker_dead_ms(self):
        rows = []
        for seed in (13, 7, 42, 99, 123):
            for cca, gp, p95 in (
                ("Reach", 80.0, 120.0),
                ("BBRv3approx", 70.0, 130.0),
                ("LeoAware", 80.0, 120.0),
            ):
                rows.append(
                    {
                        "scenario": "leo_fast_ho",
                        "seed": seed,
                        "cca": cca,
                        "goodput_mbps": gp,
                        "p95_rtt_ms": p95,
                        "flicker_dead_ms_mean": 250.0,
                        "flicker_dead_ms_p95": 400.0,
                        "flicker_dead_ms_n": 3,
                        "flicker_dead_ms_n_censored": 0,
                        "flicker_dead_ms_recover_frac": 0.80,
                    }
                )
            rows.append(
                {
                    "scenario": "terrestrial",
                    "seed": seed,
                    "cca": "Reach",
                    "goodput_mbps": 78.0,
                    "p95_rtt_ms": 40.0,
                }
            )
        summary = _summarize(rows, VelaConfig(name="Reach", seeds=[13, 7, 42, 99, 123]))
        block = summary["flicker_dead_ms"]
        self.assertEqual(block["metric"], "flicker_dead_ms")
        self.assertEqual(block["recover_frac"], 0.80)
        self.assertTrue(block["not_rtt_hop"])
        self.assertEqual(block["event_kind"], "Flicker")
        self.assertIsNotNone(block["flicker_dead_ms_mean"])
        self.assertIsNotNone(block["flicker_dead_ms_p95"])
        self.assertIn("flicker_dead_ms", honesty_text(summary["gate"]))
        self.assertIn("not RttHop", honesty_text(summary["gate"]))


if __name__ == "__main__":
    unittest.main()
