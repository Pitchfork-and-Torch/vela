"""Dead-seconds-after-handover: synthetic hop fixture + eval_law mix refuse."""
from __future__ import annotations

import unittest

from vela.dead_sec import (
    DEAD_SEC_RECOVER_FRAC,
    compute_dead_seconds,
    dead_seconds_summary,
    row_dead_sec_fields,
)
from vela.eval_harness import _summarize, honesty_text
from vela.ir import VelaConfig
from vela.receipt import (
    DEFAULT_EVAL_LAW,
    EVAL_LAW_COUPLED_RNG_V34_P95,
    EVAL_LAW_OPE_FAIR_V37,
    build_receipt,
    eval_law_mix_errors,
    stamp_eval_law,
    verify_receipt,
)


def _synthetic_hop_series():
    """One hop at t=10. Pre-hop median 100 Mbps. Dip then recover to 80%."""
    # samples every 0.05s from 0..20
    t = [i * 0.05 for i in range(0, 401)]
    hop_t = 10.0
    gps = []
    for tt in t:
        if tt < hop_t:
            gps.append(100e6)  # 100 Mbps steady
        elif tt < hop_t + 1.5:
            gps.append(10e6)  # dead / collapsed
        else:
            gps.append(85e6)  # recovered above 80% of 100
    return t, gps, [hop_t]


class TestDeadSecondsSynthetic(unittest.TestCase):
    def test_recover_frac_documented_default(self):
        self.assertEqual(DEAD_SEC_RECOVER_FRAC, 0.80)

    def test_synthetic_hop_dead_seconds(self):
        t, gp, hops = _synthetic_hop_series()
        detail = compute_dead_seconds(t, gp, hops)
        self.assertEqual(detail["recover_frac"], 0.80)
        self.assertEqual(detail["recover_pct"], 80)
        self.assertIn("pre-hop epoch median", detail["definition"])
        self.assertEqual(detail["n_hops"], 1)
        self.assertEqual(detail["n_recovered"], 1)
        self.assertEqual(detail["n_censored"], 0)
        hop = detail["hops"][0]
        self.assertAlmostEqual(hop["hop_t"], 10.0)
        self.assertAlmostEqual(hop["pre_hop_median_bps"], 100e6)
        self.assertAlmostEqual(hop["threshold_bps"], 80e6)
        # first sample at/after 11.5s hits 85e6
        self.assertAlmostEqual(hop["dead_s"], 1.5, places=3)
        self.assertFalse(hop["censored"])
        self.assertAlmostEqual(detail["dead_s_mean"], 1.5, places=3)

    def test_censored_when_never_recovers(self):
        t = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        gp = [100e6, 100e6, 5e6, 5e6, 5e6, 5e6]
        detail = compute_dead_seconds(t, gp, [2.0], end_t=5.0)
        self.assertEqual(detail["n_censored"], 1)
        self.assertTrue(detail["hops"][0]["censored"])
        self.assertAlmostEqual(detail["hops"][0]["dead_s"], 3.0)

    def test_two_hops_use_pre_hop_epoch(self):
        # Epoch0 [0,10): 50 Mbps. Epoch1 [10,20): 100 Mbps then dip.
        t = [i * 0.5 for i in range(0, 61)]  # 0..30
        gp = []
        for tt in t:
            if tt < 10.0:
                gp.append(50e6)
            elif tt < 20.0:
                gp.append(100e6)
            elif tt < 21.0:
                gp.append(10e6)
            else:
                gp.append(90e6)
        detail = compute_dead_seconds(t, gp, [10.0, 20.0], end_t=30.0)
        self.assertEqual(detail["n_hops"], 2)
        # Hop at 10: pre median 50e6, thr 40e6; post samples are 100e6 -> instant
        self.assertAlmostEqual(detail["hops"][0]["dead_s"], 0.0, places=3)
        # Hop at 20: pre median 100e6, thr 80e6; recovers at 21.0
        self.assertAlmostEqual(detail["hops"][1]["pre_hop_median_bps"], 100e6)
        self.assertAlmostEqual(detail["hops"][1]["dead_s"], 1.0, places=3)

    def test_row_and_summary_helpers(self):
        t, gp, hops = _synthetic_hop_series()
        detail = compute_dead_seconds(t, gp, hops)
        fields = row_dead_sec_fields(detail)
        self.assertEqual(fields["dead_s_n_hops"], 1)
        self.assertAlmostEqual(fields["dead_s_mean"], 1.5, places=3)
        agg = dead_seconds_summary(
            [
                {
                    "dead_s_mean": 1.5,
                    "dead_s_n_hops": 1,
                    "dead_s_n_censored": 0,
                    "dead_s_recover_frac": 0.80,
                }
            ]
        )
        self.assertEqual(agg["recover_pct"], 80)
        self.assertEqual(agg["soft_reprobe_cut"], 0.58)
        self.assertAlmostEqual(agg["dead_s_mean"], 1.5, places=3)


class TestEvalLawStamp(unittest.TestCase):
    def test_default_law_is_coupled_rng(self):
        stamp = stamp_eval_law()
        self.assertEqual(stamp["eval_law"], EVAL_LAW_COUPLED_RNG_V34_P95)
        self.assertIn("OPE-fair", stamp["eval_law_note"])

    def test_summarize_stamps_eval_law_and_dead_seconds(self):
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
                        "dead_s_mean": 0.5,
                        "dead_s_n_hops": 2,
                        "dead_s_n_censored": 0,
                        "dead_s_recover_frac": 0.80,
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
        self.assertEqual(summary["eval_law"], DEFAULT_EVAL_LAW)
        self.assertIn("eval_law=", summary["honesty"])
        self.assertEqual(summary["dead_seconds"]["recover_frac"], 0.80)
        self.assertIsNotNone(summary["dead_seconds"]["dead_s_mean"])

    def test_mix_refuse_both_landmarks(self):
        payload = {
            "eval_law": EVAL_LAW_COUPLED_RNG_V34_P95,
            "tables": [
                {"cca": "LeoAware", "goodput_mean": 73.57, "p95_mean": 138.37},
                {"cca": "OCE", "goodput_mean": 58.78, "p95_mean": 152.09},
            ],
        }
        errs = eval_law_mix_errors(payload)
        self.assertTrue(errs)
        self.assertIn("refuse", errs[0].lower())

    def test_single_era_ok(self):
        payload = {
            "eval_law": EVAL_LAW_COUPLED_RNG_V34_P95,
            "tables": [
                {"cca": "LeoAware", "goodput_mean": 73.57, "p95_mean": 138.37},
            ],
        }
        self.assertEqual(eval_law_mix_errors(payload), [])

    def test_receipt_carries_eval_law(self):
        summary = {
            "verdict": "INCOMPLETE",
            "power": "low",
            "gate": "fast",
            "honesty": honesty_text("fast"),
            "eval_law": DEFAULT_EVAL_LAW,
            "eval_law_note": stamp_eval_law()["eval_law_note"],
            "rows": [],
            "config": {
                "name": "Reach",
                "seeds": [13, 7],
                "scenarios": ["leo_fast_ho", "terrestrial"],
                "duration_s": 45.0,
            },
        }
        rec = build_receipt(
            source="controller Reach { compose Detect + SoftReprobe }",
            source_name="x.vela",
            compose=["Detect", "SoftReprobe"],
            config=summary["config"],
            summary=summary,
        )
        self.assertEqual(rec["eval_law"], EVAL_LAW_COUPLED_RNG_V34_P95)
        self.assertEqual(verify_receipt(rec, summary=summary), [])

    def test_verify_refuses_mixed_receipt(self):
        summary = {
            "verdict": "INCOMPLETE",
            "power": "low",
            "gate": "named",
            "honesty": "test",
            "eval_law": DEFAULT_EVAL_LAW,
            "rows": [],
            "config": {"name": "Reach", "seeds": [7], "scenarios": ["leo_fast_ho"], "duration_s": 45.0},
            "tables": [
                {"goodput_mean": 73.57, "p95_mean": 138.37},
                {"goodput_mean": 58.78, "p95_mean": 152.09},
            ],
        }
        rec = build_receipt(
            source="controller Reach { compose Detect }",
            source_name="x.vela",
            compose=["Detect"],
            config=summary["config"],
            summary=summary,
        )
        # Plant both landmarks on the receipt body after build (tamper / bad table).
        rec_bad = dict(rec)
        rec_bad["tables"] = summary["tables"]
        # Recompute digest would fail; verify_receipt mix check runs on receipt walk.
        errs = eval_law_mix_errors(rec_bad)
        self.assertTrue(any("mix" in e.lower() or "refuse" in e.lower() for e in errs))


if __name__ == "__main__":
    unittest.main()
