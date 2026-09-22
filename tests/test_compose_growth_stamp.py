"""Compose growth honesty: visible growth= stamp; missing clause fails closed."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import CWND_RAISERS, check
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import HOUSE_ENDPOINT_CUT

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

STAMP_MAX = (
    "growth=max  (compose growth honesty; two cwnd raisers need min|max|sum)"
)


LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(compose: str, *, growth: str | None = None, posture: str = "review") -> str:
    growth_line = f"  compose growth = {growth}\n" if growth else ""
    return f"""
lang vela 0.4
controller Probe {{
  posture {posture}
  compose {compose}
{growth_line}  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
  on Reconfig(e) {{
    invalidate min_rtt, bw
    enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
  }}
{LOSS}
}}
"""


class TestComposeGrowthStamp(unittest.TestCase):
    def test_house_cut_untouched(self):
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_cwnd_raisers_catalog(self):
        self.assertEqual(
            set(CWND_RAISERS),
            {"OCE", "HorizonChase", "TrimFill", "QuietReach", "TrimReclaim"},
        )

    def test_two_raisers_without_growth_fail_closed(self):
        src = _src("Detect + SoftReprobe + HorizonChase + TrimFill")
        res = check(parse(src, "growth-bare.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("compose growth" in e for e in res.errors))
        self.assertEqual(res.growth_compose, "")

    def test_two_raisers_with_growth_max_stamps(self):
        src = _src(
            "Detect + SoftReprobe + HorizonChase + TrimFill",
            growth="max",
        )
        res = check(parse(src, "growth-max.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.growth_compose, "max")
        self.assertIn("HorizonChase", res.closed_writes)
        self.assertIn("TrimFill", res.closed_writes)

    def test_growth_min_and_sum(self):
        for val in ("min", "sum"):
            src = _src(
                "Detect + SoftReprobe + QuietReach + TrimReclaim",
                growth=val,
            )
            res = check(parse(src, f"growth-{val}.vela"))
            self.assertTrue(res.ok, res.errors)
            self.assertEqual(res.growth_compose, val)

    def test_single_raiser_no_growth_ok_no_stamp(self):
        src = _src("Detect + SoftReprobe + HorizonChase")
        res = check(parse(src, "one-raiser.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.growth_compose, "")

    def test_reach_observe_no_stamp(self):
        res = check(
            parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.growth_compose, "")
        self.assertTrue(res.observe_only)

    def test_cli_prints_growth_stamp(self):
        src = _src(
            "Detect + SoftReprobe + HorizonChase + TrimFill",
            growth="max",
        )
        path = ROOT / "examples" / "_tmp_compose_growth_stamp.vela"
        try:
            path.write_text(src, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vela_main(["check", str(path)])
            out = buf.getvalue()
            self.assertEqual(rc, 0, out)
            self.assertIn(STAMP_MAX, out)
            self.assertIn("growth=max", out)
            self.assertIn("compose growth honesty", out)
            self.assertNotIn("growth_compose=", out)
            # SoftReprobe house cut stays 0.58 (not retuned); no dish Mbps.
            self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)
            self.assertNotIn("Mbps", out)
        finally:
            if path.exists():
                path.unlink()

    def test_cli_two_raisers_missing_growth_fails(self):
        src = _src("Detect + SoftReprobe + OCE + HorizonChase")
        path = ROOT / "examples" / "_tmp_compose_growth_bare.vela"
        try:
            path.write_text(src, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = vela_main(["check", str(path)])
            out = buf.getvalue()
            self.assertEqual(rc, 1, out)
            self.assertIn("compose growth", out)
            self.assertNotIn("growth=", out)
        finally:
            if path.exists():
                path.unlink()

    def test_reach_check_omits_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertNotIn("growth=", out)
        self.assertIn("observe-only", out)
        self.assertIn("house cut 0.58", out)

    def test_docs_name_visible_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        ingress = (ROOT / "docs" / "INGRESS.md").read_text(encoding="utf-8")
        self.assertIn("growth=min|max|sum", lang)
        self.assertIn("compose growth honesty", lang)
        self.assertIn("growth=", equinox)
        self.assertIn("Compose growth honesty", ingress)
        self.assertIn("fails closed", ingress)


if __name__ == "__main__":
    unittest.main()
