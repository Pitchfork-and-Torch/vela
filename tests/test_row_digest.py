"""row_digest must not crash on null or junk metrics."""
from __future__ import annotations

import unittest

from vela.digest import row_digest
from vela.receipt import rows_merkle


def _base(**kw):
    row = {
        "scenario": "leo_fast_ho",
        "seed": 7,
        "cca": "Reach",
        "goodput_mbps": 88.65,
        "p95_rtt_ms": 108.4,
    }
    row.update(kw)
    return row


class TestRowDigestNullMetrics(unittest.TestCase):
    def test_null_goodput_matches_missing(self):
        # explicit null used to raise TypeError inside float()
        null_gp = _base(goodput_mbps=None)
        missing = {
            "scenario": "leo_fast_ho",
            "seed": 7,
            "cca": "Reach",
            "p95_rtt_ms": 108.4,
        }
        self.assertEqual(row_digest(null_gp), row_digest(missing))

    def test_null_p95_does_not_raise(self):
        digest = row_digest(_base(p95_rtt_ms=None))
        self.assertEqual(len(digest), 64)

    def test_junk_metric_coerces_like_zero(self):
        junk = row_digest(_base(goodput_mbps="not-a-number"))
        zero = row_digest(_base(goodput_mbps=0.0))
        self.assertEqual(junk, zero)

    def test_rows_merkle_survives_null_row(self):
        rows = [_base(), _base(seed=13, goodput_mbps=None)]
        merkle = rows_merkle(rows)
        self.assertEqual(len(merkle), 64)


if __name__ == "__main__":
    unittest.main()
