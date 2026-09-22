"""Passthrough stamp: on/when/every cannot invent capacity (pace/cwnd/chase)."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check, cruise_write_error
from vela.cli import main as vela_main
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

STAMP = "passthrough  (on/when/every cannot invent pace/cwnd/chase; LeoAware wrap)"


class TestPassthroughStamp(unittest.TestCase):
    def test_reach_is_passthrough(self):
        res = check(parse((EX / "reach.vela").read_text(encoding="utf-8"), "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.passthrough)
        self.assertTrue(res.observe_only)

    def test_reach_check_prints_explicit_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "reach.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(STAMP, out)
        self.assertIn("cannot invent pace/cwnd/chase", out)
        self.assertIn("on/when/every", out)
        # Old vague cruise-only gloss must not remain the stamp.
        self.assertNotIn("passthrough  (LeoAware wrap; no cruise write)", out)

    def test_ascent_check_prints_explicit_stamp(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = vela_main(["check", str(EX / "ascent.vela")])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn(STAMP, out)

    def test_docs_name_invent_capacity_stamp(self):
        lang = (ROOT / "docs" / "LANGUAGE.md").read_text(encoding="utf-8")
        equinox = (ROOT / "docs" / "EQUINOX.md").read_text(encoding="utf-8")
        for doc in (lang, equinox):
            self.assertIn("cannot invent", doc)
            self.assertIn("pace", doc)
            self.assertIn("cwnd", doc)
            self.assertIn("chase", doc)
            self.assertIn("on/when/every", doc)

    def test_error_helper_names_invent_capacity(self):
        msg = cruise_write_error("Probe", "pace =")
        self.assertIn("invent-capacity", msg)
        self.assertIn("on/when/every", msg)
        self.assertIn("pace/cwnd/chase", msg)


class TestOnInventCapacity(unittest.TestCase):
    def test_observe_on_pace_is_not_passthrough(self):
        """pace inside on Reconfig invents capacity; SoftReprobe cut/enter stay legal."""
        src = """
lang vela 0.1
controller Probe {
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
  on Reconfig(e) match e {
    RttHop => {
      when bw.n >= 2 {
        pace = bw.mid
      }
    }
    Flicker => hold
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "on-pace.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.passthrough)
        self.assertIn(cruise_write_error("Probe", "pace ="), res.errors)

    def test_observe_on_chase_is_not_passthrough(self):
        src = """
lang vela 0.1
controller Probe {
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => {
      chase delivery toward 1
    }
    Flicker => hold
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "on-chase.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.passthrough)
        self.assertIn(cruise_write_error("Probe", "chase"), res.errors)

    def test_observe_on_cwnd_is_not_passthrough(self):
        src = """
lang vela 0.1
controller Probe {
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => { cwnd = 10 }
    Flicker => hold
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "on-cwnd.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.passthrough)
        self.assertIn(cruise_write_error("Probe", "cwnd ="), res.errors)

    def test_observe_on_reprobe_cut_still_passthrough(self):
        src = """
lang vela 0.1
controller Probe {
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
    Flicker => {
      invalidate min_rtt, bw
      enter Reprobe(cut: 0.58, explore: 1.15 * rtt, fill: 1.85 * rtt)
    }
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "on-reprobe.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.passthrough)

    def test_observe_hint_some_pace_is_not_passthrough(self):
        src = """
lang vela 0.1
use std.hint
controller Probe {
  posture observe
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    hint: Hint<PathHint>
  on Hint(h) match h {
    Some => { pace = 1 }
    None => hold
  }
  on Reconfig(e) match e {
    RttHop => hold
    Flicker => hold
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "hint-pace.vela"))
        self.assertFalse(res.ok)
        self.assertFalse(res.passthrough)
        self.assertIn(cruise_write_error("Probe", "pace ="), res.errors)


if __name__ == "__main__":
    unittest.main()
