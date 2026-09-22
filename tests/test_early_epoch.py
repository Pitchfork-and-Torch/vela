"""Early-epoch IntervalBw: a tight band in the first 2 RTT is an observe error."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check, early_epoch_point_error, early_epoch_tight_error
from vela.cli import main
from vela.ir import program_to_config
from vela.parser import parse
from vela.receipt import build_receipt, verify_receipt
from vela.types import (
    EARLY_EPOCH_MIN_RTTS,
    EARLY_EPOCH_TIGHT_UNCERT,
    HOUSE_ENDPOINT_CUT,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(
    body: str,
    posture: str = "observe",
    compose: str = "Detect + IntervalBw",
) -> str:
    return f"""
lang vela 0.1
controller Probe {{
  posture {posture}
  compose {compose}
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
    delay_ratio: Ratio
{body}
{LOSS}
}}
"""


class TestEarlyEpochLaw(unittest.TestCase):
    def test_constants_stay_house(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)
        self.assertEqual(EARLY_EPOCH_MIN_RTTS, 2.0)
        self.assertEqual(EARLY_EPOCH_TIGHT_UNCERT, 0.40)

    def test_point_read_inside_first_two_rtt_is_error(self):
        src = _src(
            """
  when epoch.age < 2 * rtt {
    when bw.n >= 2 {
      let x = bw.mid
    }
  }
"""
        )
        res = check(parse(src, "early-age.vela"))
        self.assertFalse(res.ok)
        self.assertIn(early_epoch_point_error("Probe", "bw"), res.errors)

    def test_point_read_inside_first_two_rtts_count_is_error(self):
        src = _src(
            """
  when epoch.rtts < 2 {
    when bw.n >= 2 {
      let x = bw.lo
    }
  }
"""
        )
        res = check(parse(src, "early-count.vela"))
        self.assertFalse(res.ok)
        self.assertIn(early_epoch_point_error("Probe", "bw"), res.errors)

    def test_mature_age_guard_allows_n_ge_2_point(self):
        src = _src(
            """
  when epoch.age >= 2 * rtt {
    when bw.n >= 2 {
      let x = bw.mid
    }
  }
"""
        )
        res = check(parse(src, "mature-age.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_n_ge_2_alone_stays_the_older_law(self):
        src = _src(
            """
  when bw.n >= 2 {
    let x = bw.hi
  }
"""
        )
        res = check(parse(src, "n2.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_tight_uncertainty_without_mature_guard_is_error(self):
        src = _src(
            """
  when uncertainty <= 0.40 {
    let n = bw.n
  }
"""
        )
        res = check(parse(src, "tight-when.vela"))
        self.assertFalse(res.ok)
        self.assertIn(early_epoch_tight_error("Probe"), res.errors)

    def test_interval_uncertainty_attr_is_the_same_tight_claim(self):
        src = _src(
            """
  when bw.uncertainty <= 0.40 {
    let n = bw.n
  }
"""
        )
        res = check(parse(src, "tight-attr.vela"))
        self.assertFalse(res.ok)
        self.assertIn(early_epoch_tight_error("Probe"), res.errors)

    def test_tight_assign_without_mature_guard_is_error(self):
        src = _src(
            """
  every ack {
    uncertainty = 0.40
  }
"""
        )
        res = check(parse(src, "tight-assign.vela"))
        self.assertFalse(res.ok)
        self.assertIn(early_epoch_tight_error("Probe"), res.errors)

    def test_uncertainty_above_floor_is_ok(self):
        src = _src(
            """
  every ack {
    uncertainty = 0.41
  }
  when uncertainty <= 0.41 {
    let n = bw.n
  }
"""
        )
        res = check(parse(src, "wide.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_one_rtt_guard_does_not_license_a_tight_band(self):
        src = _src(
            """
  when epoch.age >= 1 * rtt {
    when uncertainty <= 0.40 {
      let n = bw.n
    }
  }
"""
        )
        res = check(parse(src, "one-rtt.vela"))
        self.assertFalse(res.ok)
        self.assertIn(early_epoch_tight_error("Probe"), res.errors)

    def test_rtts_greater_than_one_does_not_license_a_tight_band(self):
        src = _src(
            """
  when epoch.rtts > 1 {
    when uncertainty <= 0.40 {
      let n = bw.n
    }
  }
"""
        )
        res = check(parse(src, "gt1.vela"))
        self.assertFalse(res.ok)
        self.assertIn(early_epoch_tight_error("Probe"), res.errors)

    def test_mature_rtts_guard_allows_tight_uncertainty(self):
        src = _src(
            """
  when epoch.rtts >= 2 {
    when uncertainty <= 0.40 {
      let n = bw.n
    }
  }
"""
        )
        res = check(parse(src, "mature-count.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_else_of_mature_age_is_early(self):
        src = _src(
            """
  every ack {
    if epoch.age >= 2 * rtt then let n = bw.n else {
      when bw.n >= 2 {
        let x = bw.mid
      }
    }
  }
"""
        )
        res = check(parse(src, "else-early.vela"))
        self.assertFalse(res.ok)
        self.assertIn(early_epoch_point_error("Probe", "bw"), res.errors)

    def test_review_may_name_the_early_tight_band(self):
        src = _src(
            """
  when epoch.age < 2 * rtt {
    when bw.n >= 2 {
      let x = bw.mid
    }
  }
  every ack {
    uncertainty = 0.20
  }
""",
            posture="review",
        )
        res = check(parse(src, "review.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_law_does_not_fire_without_an_interval(self):
        src = """
lang vela 0.1
controller Probe {
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    delay_ratio: Ratio
  every ack {
    uncertainty = 0.10
  }
""" + LOSS + "\n}\n"
        res = check(parse(src, "no-interval.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertNotIn(early_epoch_tight_error("Probe"), res.errors)

    def test_interval_bw_compose_refuses_tight_without_a_signal(self):
        src = """
lang vela 0.1
controller Probe {
  posture observe
  compose Detect + IntervalBw
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    delay_ratio: Ratio
  every ack {
    uncertainty = 0.20
  }
""" + LOSS + "\n}\n"
        res = check(parse(src, "compose-only.vela"))
        self.assertFalse(res.ok)
        self.assertIn(early_epoch_tight_error("Probe"), res.errors)


class TestEarlyEpochStamp(unittest.TestCase):
    def test_reach_and_ascent_still_check(self):
        for name in ("reach.vela", "ascent.vela"):
            src = (EX / name).read_text(encoding="utf-8")
            prog = parse(src, name)
            res = check(prog)
            self.assertTrue(res.ok, (name, res.errors))
            self.assertEqual(res.early_epoch_rtts, EARLY_EPOCH_MIN_RTTS)
            self.assertEqual(res.early_epoch_tight, EARLY_EPOCH_TIGHT_UNCERT)
            cfg = program_to_config(prog)
            self.assertEqual(cfg.early_epoch_rtts, EARLY_EPOCH_MIN_RTTS)
            self.assertEqual(cfg.early_epoch_tight_uncert, EARLY_EPOCH_TIGHT_UNCERT)
            self.assertIn("IntervalBw", cfg.mechanisms)
            self.assertNotIn("HorizonChase", cfg.mechanisms)

    def test_check_cli_stamps_early_epoch(self):
        for name in ("reach.vela", "ascent.vela"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["check", str(EX / name)])
            out = buf.getvalue()
            self.assertEqual(rc, 0, (name, out))
            self.assertIn("observe-only", out)
            self.assertIn("early-epoch=2rtt", out)
            self.assertIn("uncertainty floor 0.4", out)
            self.assertNotIn("Mbps", out)

    def test_receipt_stamps_the_same_constants(self):
        rec = build_receipt(
            source="lang vela 0.1\n",
            source_name="t.vela",
            compose=["Detect", "SoftReprobe", "IntervalBw"],
            config={"seeds": [7], "duration_s": 45.0, "scenarios": ["leo_fast_ho"]},
            summary={
                "verdict": "INCOMPLETE",
                "power": "low",
                "honesty": "test",
                "rows": [],
                "gate": "fast",
            },
        )
        self.assertEqual(rec["early_epoch_rtts"], EARLY_EPOCH_MIN_RTTS)
        self.assertEqual(rec["early_epoch_tight_uncert"], EARLY_EPOCH_TIGHT_UNCERT)
        self.assertEqual(verify_receipt(rec), [])


if __name__ == "__main__":
    unittest.main()
