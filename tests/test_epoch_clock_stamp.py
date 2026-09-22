"""Epoch-clock honesty is a visible vela check stamp."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import (
    check,
    hybrid_tick_error,
    wall_clock_capacity_error,
)
from vela.cli import main as vela_main
from vela.parser import parse
from vela.types import (
    EPOCH_CLOCK_CHECK_LINE,
    EPOCH_CLOCK_STAMP,
    HOUSE_ENDPOINT_CUT,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

STAMP = EPOCH_CLOCK_CHECK_LINE

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(body: str, *, posture: str = "review") -> str:
    return f"""
lang vela 0.4
controller Probe {{
  posture {posture}
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
{body}
{LOSS}
}}
"""


class TestEpochClockStamp(unittest.TestCase):
    def test_stamp_constants(self):
        self.assertEqual(EPOCH_CLOCK_STAMP, "epoch-clock")
        self.assertIn("advances on ack|reconfig", STAMP)
        self.assertIn("refuse wall-clock capacity", STAMP)
        self.assertEqual(HOUSE_ENDPOINT_CUT, 0.58)

    def test_reach_is_epoch_clock(self):
        res = check(
            parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela")
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.epoch_clock)
        self.assertTrue(res.hybrid)

    def test_equinox_is_epoch_clock(self):
        res = check(
            parse(
                (EX / "equinox.vela").read_text(encoding="utf-8"), "equinox.vela"
            )
        )
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.epoch_clock)

    def test_reach_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(STAMP, out)
        self.assertIn("epoch-clock", out)
        self.assertIn("advances on ack|reconfig", out)
        self.assertIn("refuse wall-clock capacity", out)
        self.assertIn("0.58", out)

    def test_equinox_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "equinox.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(STAMP, out)

    def test_ascent_check_prints_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "ascent.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(STAMP, out)

    def test_wall_capacity_refused(self):
        src = _src(
            """
  on Reconfig(e) match e {
    RttHop => {
      pace = wall_capacity
    }
    Flicker => hold
  }
"""
        )
        res = check(parse(src, "wall-cap.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.epoch_clock)
        self.assertIn(
            wall_clock_capacity_error("Probe", "wall_capacity"),
            res.errors,
        )

    def test_every_wall_tick_clears_epoch_clock(self):
        src = _src(
            """
  every wall {
    hold
  }
"""
        )
        res = check(parse(src, "every-wall.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.hybrid)
        self.assertFalse(res.epoch_clock)
        self.assertIn(hybrid_tick_error("Probe", "wall"), res.errors)

    def test_docs_name_visible_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        for doc in (lang, equinox):
            self.assertIn("epoch-clock", doc)
            self.assertIn("advances on ack|reconfig", doc)
            self.assertIn("refuse wall-clock capacity", doc)
        self.assertIn("Epoch-clock", equinox)
        self.assertIn("Epoch-clock law", lang)


if __name__ == "__main__":
    unittest.main()
