"""Kernel surface tests (import LeoAware if present)."""
from __future__ import annotations

import unittest
from pathlib import Path

from vela.ir import VelaConfig
from vela.kernel import HorizonCCA, make_cca


class TestKernel(unittest.TestCase):
    def test_factory_and_ack(self):
        leo = Path.home() / "Projects" / "leo-aware-transport"
        if not leo.is_dir():
            self.skipTest("leo-aware-transport missing")
        cca = make_cca(VelaConfig())()
        self.assertEqual(cca.name, "Horizon")
        cca.on_ack(0.5, 0.04, 1200, 0)
        st = cca.state()
        self.assertGreater(st.cwnd_bytes, 0)
        n = cca.can_send(0.51)
        self.assertGreaterEqual(n, 0)

    def test_predictive_p_ho_starts_zero(self):
        leo = Path.home() / "Projects" / "leo-aware-transport"
        if not leo.is_dir():
            self.skipTest("leo-aware-transport missing")
        h = HorizonCCA(VelaConfig())
        self.assertEqual(h.p_ho, 0.0)


if __name__ == "__main__":
    unittest.main()
