"""Uncertainty law: Interval used as a point requires n >= 2."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import check, interval_point_error
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(body: str) -> str:
    return f"""
lang vela 0.1
controller Probe {{
  compose Detect + IntervalBw
  signals:
    epoch: Epoch
    bw: Interval<bps> @ epoch
    delay_ratio: Ratio
{body}
{LOSS}
}}
"""


class TestIntervalN2(unittest.TestCase):
    def test_bare_interval_as_point_is_error(self):
        src = _src(
            """
  when p_ho > 0.5 {
    pace = bw
  }
"""
        )
        res = check(parse(src, "bare.vela"))
        self.assertFalse(res.ok)
        self.assertIn(interval_point_error("Probe", "bw"), res.errors)

    def test_interval_mid_unguarded_is_error(self):
        src = _src(
            """
  when p_ho > 0.5 {
    pace = bw.mid
  }
"""
        )
        res = check(parse(src, "mid.vela"))
        self.assertFalse(res.ok)
        self.assertIn(
            "Probe: Interval bw used as a point requires bw.n >= 2 (uncertainty law)",
            res.errors,
        )

    def test_interval_mid_under_when_n_ge_2_ok(self):
        src = _src(
            """
  when bw.n >= 2 {
    pace = bw.mid
  }
"""
        )
        res = check(parse(src, "guarded.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_interval_n_read_always_ok(self):
        src = _src(
            """
  when p_ho > 0.5 {
    let count = bw.n
  }
"""
        )
        res = check(parse(src, "count.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_require_n_ge_2_then_assign_ok(self):
        src = _src(
            """
  when p_ho > 0.5 {
    require bw.n >= 2 then pace = bw.lo
  }
"""
        )
        res = check(parse(src, "require.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_if_n_ge_2_then_assign_ok(self):
        src = _src(
            """
  when p_ho > 0.5 {
    if bw.n >= 2 then pace = bw.hi
  }
"""
        )
        res = check(parse(src, "if.vela"))
        self.assertTrue(res.ok, res.errors)

    def test_let_bare_interval_is_error(self):
        src = _src(
            """
  every ack {
    let x = bw
  }
"""
        )
        res = check(parse(src, "let.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("uncertainty law" in e for e in res.errors))

    def test_chase_toward_interval_is_error(self):
        src = _src(
            """
  every ack {
    chase cwnd toward bw
  }
"""
        )
        res = check(parse(src, "chase.vela"))
        self.assertFalse(res.ok)
        self.assertIn(interval_point_error("Probe", "bw"), res.errors)

    def test_existing_examples_still_check(self):
        for name in ("horizon.vela", "reach.vela", "luff.vela"):
            src = (EX / name).read_text(encoding="utf-8")
            res = check(parse(src, name))
            self.assertTrue(res.ok, (name, res.errors))


if __name__ == "__main__":
    unittest.main()
