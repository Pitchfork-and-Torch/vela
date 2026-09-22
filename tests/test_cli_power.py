"""vela power labels seeds without DualGate claims."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from vela.cli import main


class TestCliPower(unittest.TestCase):
    def test_house_five_is_low(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["power", "--seeds", "13,7,42,99,123"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("power=low", out)
        self.assertIn("n=5", out)
        self.assertIn("Not a dual-gate win", out)

    def test_eight_is_ok(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["power", "--seeds", "13,7,42,99,123,17,19,23"])
        self.assertEqual(rc, 0)
        self.assertIn("power=ok", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
