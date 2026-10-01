"""WriteCap is linear: split partitions budget, borrow spends it."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.checker import (
    check,
    writecap_ambient_error,
    writecap_exhausted_error,
    writecap_reuse_error,
    writecap_split_sum_error,
    writecap_target_error,
    writecap_unknown_error,
)
from vela.parser import ParseError, parse

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"

LOSS = """
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
"""


def _src(body: str, *, authority: str = "cwnd: 2, pace: 0") -> str:
    return f"""
lang vela 0.3
controller Probe {{
  posture review
  compose Detect + IntervalBw
  authority {{ {authority} }}
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
    cap: WriteCap<cwnd> @ epoch
{body}
{LOSS}
}}
"""


class TestWriteCapBudget(unittest.TestCase):
    def test_equinox_is_integer_budget(self):
        src = (EX / "equinox.vela").read_text(encoding="utf-8")
        res = check(parse(src, "equinox.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.writecap, "budget")
        self.assertTrue(res.affine)

    def test_reach_has_no_writecap(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.writecap, "")
        self.assertTrue(res.passthrough)
        self.assertTrue(res.affine)
        self.assertTrue(res.no_oracle)

    def test_budget_zero_still_blocks_ambient(self):
        src = _src(
            """
  when p_ho > 0.5 {
    pace = bw
  }
""",
            authority="cwnd: 0, pace: 0",
        )
        res = check(parse(src, "budget0.vela"))
        self.assertFalse(res.ok)
        self.assertEqual(res.writecap, "budget")
        self.assertIn(writecap_exhausted_error("Probe", 1, 0), res.errors)


class TestWriteCapLinear(unittest.TestCase):
    def test_split_and_borrow_two_writes(self):
        src = _src(
            """
  split cap into fill, hold
  when bw.n >= 2 {
    borrow fill {
      cwnd = bw.mid
    }
  }
  when bw.n >= 2 {
    borrow hold {
      cwnd = bw.lo
    }
  }
"""
        )
        res = check(parse(src, "split-ok.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.writecap, "linear")

    def test_weighted_split(self):
        src = _src(
            """
  split cap into fill:1, hold:1
  when bw.n >= 2 {
    borrow fill {
      cwnd = bw.mid
    }
  }
  when bw.n >= 2 {
    borrow hold {
      cwnd = bw.mid
    }
  }
"""
        )
        res = check(parse(src, "weighted.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.writecap, "linear")

    def test_borrow_without_split(self):
        src = _src(
            """
  when bw.n >= 2 {
    borrow cap {
      cwnd = bw.mid
    }
  }
""",
            authority="cwnd: 1",
        )
        res = check(parse(src, "borrow-one.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.writecap, "linear")

    def test_ambient_write_after_split_is_error(self):
        src = _src(
            """
  split cap into fill, hold
  when bw.n >= 2 {
    cwnd = bw.mid
  }
"""
        )
        res = check(parse(src, "ambient.vela"))
        self.assertFalse(res.ok)
        self.assertEqual(res.writecap, "linear")
        self.assertIn(writecap_ambient_error("Probe", "cwnd ="), res.errors)

    def test_double_borrow_is_error(self):
        src = _src(
            """
  when bw.n >= 2 {
    borrow cap {
      cwnd = bw.mid
    }
  }
  when bw.n >= 2 {
    borrow cap {
      cwnd = bw.lo
    }
  }
""",
            authority="cwnd: 2",
        )
        res = check(parse(src, "double.vela"))
        self.assertFalse(res.ok)
        self.assertIn(writecap_reuse_error("Probe", "cap"), res.errors)

    def test_borrow_after_split_parent_is_consumed(self):
        src = _src(
            """
  split cap into fill, hold
  when bw.n >= 2 {
    borrow cap {
      cwnd = bw.mid
    }
  }
"""
        )
        res = check(parse(src, "parent.vela"))
        self.assertFalse(res.ok)
        self.assertIn(writecap_reuse_error("Probe", "cap"), res.errors)

    def test_wrong_target_is_error(self):
        src = _src(
            """
  when bw.n >= 2 {
    borrow cap {
      pace = bw.mid
    }
  }
""",
            authority="cwnd: 1",
        )
        res = check(parse(src, "target.vela"))
        self.assertFalse(res.ok)
        self.assertIn(writecap_target_error("Probe", "cap", "cwnd", "pace"), res.errors)

    def test_split_weight_mismatch(self):
        src = _src(
            """
  split cap into fill:2, hold:2
  when bw.n >= 2 {
    borrow fill {
      cwnd = bw.mid
    }
  }
"""
        )
        res = check(parse(src, "sum.vela"))
        self.assertFalse(res.ok)
        self.assertIn(writecap_split_sum_error("Probe", "cap", 2, 4), res.errors)

    def test_unweighted_split_needs_budget_eq_arity(self):
        src = _src(
            """
  split cap into a, b, c
""",
            authority="cwnd: 2",
        )
        res = check(parse(src, "arity.vela"))
        self.assertFalse(res.ok)
        self.assertIn(writecap_split_sum_error("Probe", "cap", 2, 3), res.errors)

    def test_unknown_borrow_is_error(self):
        src = _src(
            """
  when bw.n >= 2 {
    borrow nope {
      cwnd = bw.mid
    }
  }
""",
            authority="cwnd: 1",
        )
        res = check(parse(src, "nope.vela"))
        self.assertFalse(res.ok)
        self.assertIn(writecap_unknown_error("Probe", "nope"), res.errors)

    def test_borrow_budget_zero_exhausted(self):
        src = _src(
            """
  when bw.n >= 2 {
    borrow cap {
      cwnd = bw.mid
    }
  }
""",
            authority="cwnd: 0",
        )
        res = check(parse(src, "zero-borrow.vela"))
        self.assertFalse(res.ok)
        self.assertIn(writecap_exhausted_error("Probe", 1, 0), res.errors)

    def test_two_writes_in_one_borrow_need_budget_two(self):
        src = _src(
            """
  when bw.n >= 2 {
    borrow cap {
      let b = bw.mid
      cwnd = b
      cwnd = b
    }
  }
""",
            authority="cwnd: 1",
        )
        res = check(parse(src, "two-writes.vela"))
        self.assertFalse(res.ok)
        self.assertIn(writecap_exhausted_error("Probe", 2, 1), res.errors)

    def test_nested_split(self):
        src = _src(
            """
  split cap into left:1, right:1
  split right into a:1
""",
            authority="cwnd: 2",
        )
        # one-child split is a parse error
        with self.assertRaises(ParseError):
            parse(src, "nested-bad.vela")

    def test_nested_split_two_way(self):
        src = """
lang vela 0.3
controller Probe {
  posture review
  compose Detect + IntervalBw
  authority { cwnd: 3 }
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
    bw: Interval<bps> @ epoch
    cap: WriteCap<cwnd> @ epoch
  split cap into left:1, rest:2
  split rest into a:1, b:1
  when bw.n >= 2 {
    borrow left {
      cwnd = bw.mid
    }
  }
  when bw.n >= 2 {
    borrow a {
      cwnd = bw.mid
    }
  }
  when bw.n >= 2 {
    borrow b {
      cwnd = bw.lo
    }
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "nested.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.writecap, "linear")

    def test_flagship_examples_still_check(self):
        for name in (
            "reach.vela",
            "fair.vela",
            "equinox.vela",
            "horizon.vela",
            "ascent.vela",
            "luff.vela",
        ):
            src = (EX / name).read_text(encoding="utf-8")
            res = check(parse(src, name))
            self.assertTrue(res.ok, (name, res.errors))


if __name__ == "__main__":
    unittest.main()
