"""prior.bw / prior.bdp mandatory discount (<=0.75 in first 2s) is checkable."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    check,
    controller_stamps_prior_scale_discount,
    prior_scale_discount_error,
)
from vela.cli import main as vela_main
from vela.kernel import discounted_prior_scale, prior_scale_ok
from vela.parser import parse
from vela.types import (
    HOUSE_PRIOR_DISCOUNT_WINDOW_S,
    HOUSE_PRIOR_SCALE_DISCOUNT,
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


def _src(body: str, *, posture: str = "observe", compose: str = "Detect + SoftReprobe + IntervalBw") -> str:
    return f"""
lang vela 0.1
controller Scale {{
  posture {posture}
  compose {compose}
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
{body}
{LOSS}
}}
"""


RECONFIG = """
  on Reconfig(e) match e {{
    RttHop => {{
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
{extra}    }}
    Flicker => {{
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }}
  }}
"""


class TestHouseConstants(unittest.TestCase):
    def test_discount_is_075_in_first_2s(self):
        self.assertAlmostEqual(HOUSE_PRIOR_SCALE_DISCOUNT, 0.75)
        self.assertAlmostEqual(HOUSE_PRIOR_DISCOUNT_WINDOW_S, 2.0)


class TestKernelDiscount(unittest.TestCase):
    def test_early_window_rejects_scale_above_cap(self):
        self.assertFalse(prior_scale_ok(0.9, 1.0))
        self.assertFalse(prior_scale_ok(1.0, 0.0))
        self.assertTrue(prior_scale_ok(0.75, 1.0))
        self.assertTrue(prior_scale_ok(0.5, 1.5))

    def test_after_window_allows_full_scale(self):
        self.assertTrue(prior_scale_ok(1.0, 2.0))
        self.assertTrue(prior_scale_ok(1.0, 5.0))

    def test_discounted_prior_caps_early(self):
        self.assertAlmostEqual(discounted_prior_scale(100.0, 1.0, 1.0), 75.0)
        self.assertAlmostEqual(discounted_prior_scale(100.0, 1.0, 0.9), 75.0)
        self.assertAlmostEqual(discounted_prior_scale(100.0, 1.0, 0.5), 50.0)
        self.assertAlmostEqual(discounted_prior_scale(100.0, 3.0, 1.0), 100.0)


class TestCheckerStamp(unittest.TestCase):
    def test_softreprobe_stamps(self):
        src = _src(RECONFIG.format(extra=""), compose="Detect + SoftReprobe")
        res = check(parse(src, "soft.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.prior_scale_discount, HOUSE_PRIOR_SCALE_DISCOUNT)
        self.assertTrue(controller_stamps_prior_scale_discount(parse(src, "soft.vela").controllers[0]))

    def test_intervalbw_alone_stamps(self):
        src = _src(RECONFIG.format(extra=""), compose="Detect + IntervalBw")
        res = check(parse(src, "ibw.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.prior_scale_discount, 0.75)

    def test_detect_alone_no_stamp(self):
        src = _src(RECONFIG.format(extra=""), compose="Detect")
        res = check(parse(src, "detect.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertIsNone(res.prior_scale_discount)

    def test_reach_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("prior-scale-discount<=0.75", out)
        self.assertIn("prior.bw/prior.bdp", out)
        self.assertIn("first 2s", out)

    def test_equinox_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("prior-scale-discount<=0.75", out)


class TestObserveRefuse(unittest.TestCase):
    def test_bare_prior_bw_fail_closed(self):
        src = _src(RECONFIG.format(extra="      bw = prior.bw\n"))
        res = check(parse(src, "bare-bw.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("prior.bw" in e and "0.75" in e for e in res.errors),
            res.errors,
        )
        self.assertIn(
            prior_scale_discount_error("Scale", "bw = 1 * prior.bw"),
            res.errors,
        )

    def test_over_discount_prior_bw_fail_closed(self):
        src = _src(RECONFIG.format(extra="      bw = 0.9 * prior.bw\n"))
        res = check(parse(src, "over-bw.vela"))
        self.assertFalse(res.ok)
        self.assertIn(
            prior_scale_discount_error("Scale", "bw = 0.9 * prior.bw"),
            res.errors,
        )

    def test_over_discount_prior_bdp_fail_closed(self):
        src = _src(RECONFIG.format(extra="      cwnd = 0.9 * prior.bdp\n"))
        res = check(parse(src, "over-bdp.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(
            any("prior.bdp" in e and "0.75" in e for e in res.errors),
            res.errors,
        )

    def test_at_cap_prior_bw_ok(self):
        src = _src(RECONFIG.format(extra="      bw = 0.75 * prior.bw\n"))
        res = check(parse(src, "at-cap.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.prior_scale_discount, 0.75)

    def test_under_cap_prior_bw_ok(self):
        src = _src(RECONFIG.format(extra="      bw = 0.5 * prior.bw\n"))
        res = check(parse(src, "under.vela"))
        self.assertTrue(res.ok, res.errors)


class TestReviewWarn(unittest.TestCase):
    def test_review_over_discount_warns(self):
        src = _src(
            RECONFIG.format(extra="      bw = 0.9 * prior.bw\n"),
            posture="review",
        )
        res = check(parse(src, "review-over.vela"))
        self.assertTrue(
            any("mandatory discount" in w for w in res.warnings),
            res.warnings,
        )
        self.assertFalse(
            any("observe-only refuses" in e for e in res.errors),
            res.errors,
        )


class TestDocs(unittest.TestCase):
    def test_language_names_stamp(self):
        text = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        self.assertIn("prior-scale-discount<=0.75", text)
        self.assertIn("prior.bw", text)
        self.assertIn("prior.bdp", text)
        self.assertIn("0.75", text)
        self.assertIn("do not retune", text.lower())

    def test_equinox_names_stamp(self):
        text = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        self.assertIn("prior-scale-discount<=0.75", text)
        self.assertIn("prior.bw", text)
        self.assertIn("prior.bdp", text)


if __name__ == "__main__":
    unittest.main()
