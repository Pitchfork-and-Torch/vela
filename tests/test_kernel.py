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

    def test_quiet_reach_does_not_fire_at_startup(self):
        leo = Path.home() / "Projects" / "leo-aware-transport"
        if not leo.is_dir():
            self.skipTest("leo-aware-transport missing")
        h = HorizonCCA(
            VelaConfig(name="Reach", quiet_reach=True, trim_hold=True, interval_bw=True)
        )
        h.on_ack(0.5, 0.04, 1200, 0)
        self.assertEqual(h._apsis_shots, 0)
        self.assertNotEqual(h.vela_mode, "reach_apsis")


if __name__ == "__main__":
    unittest.main()
