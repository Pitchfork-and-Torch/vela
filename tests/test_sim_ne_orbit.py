"""sim!=orbit honesty: LeoPath is Starlink-class, not a cell/orbit replay."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.ast import PathModel
from vela.checker import check
from vela.cli import main
from vela.parser import parse
from vela.path import (
    SIM_NE_ORBIT,
    PathLaw,
    has_honesty_label,
    parse_path_model,
    path_mixes_csv_parametric,
    sim_ne_orbit_warning,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def _prog(path_body: str) -> str:
    return f"""
lang vela 0.1
use std.epoch
use std.loss
use std.measure
use std.path
controller Probe {{
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {{
    RttHop => hold
    Flicker => hold
  }}
  on Loss(k) match k {{
    Mobility => hold
    Congestive => cut(0.72)
    Unknown => hold
  }}
}}
{path_body}
"""


class TestSimNeOrbit(unittest.TestCase):
    def test_house_leofastho_warns_and_stamps(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
"""
        )
        res = check(parse(src, "t.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any(SIM_NE_ORBIT in w for w in res.warnings))
        self.assertIn(SIM_NE_ORBIT, res.path_bound)
        self.assertTrue(
            any("Starlink-class" in w for w in res.warnings),
            res.warnings,
        )

    def test_honesty_label_suppresses_leo_warning(self):
        src = _prog(
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
  honesty ~ "sim!=orbit"
}
"""
        )
        res = check(parse(src, "labeled.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertFalse(
            any(SIM_NE_ORBIT in w for w in res.warnings),
            res.warnings,
        )
        # Stamp still carries the honesty token on leo rails.
        self.assertIn(SIM_NE_ORBIT, res.path_bound)

    def test_mix_from_csv_parametric_without_label_warns(self):
        law = PathLaw(
            name="LeoFastHO",
            scenario="leo_fast_ho",
            fields={
                "from_csv": "tests/fixtures/starlink_tiny.csv",
                "handover": "every 12s jitter 4s",
            },
            handover_interval_s=12.0,
            handover_jitter_s=4.0,
        )
        self.assertTrue(path_mixes_csv_parametric(law))
        warn = sim_ne_orbit_warning(law)
        self.assertIsNotNone(warn)
        self.assertIn(SIM_NE_ORBIT, warn)
        self.assertIn("mixes from_csv", warn)
        self.assertIn(SIM_NE_ORBIT, law.stamp())

    def test_mix_with_honesty_label_no_mix_warning(self):
        law = PathLaw(
            name="LeoFastHO",
            scenario="leo_fast_ho",
            fields={
                "from_csv": "trace.csv",
                "handover": "every 12s jitter 4s",
                "honesty": "sim!=orbit",
            },
            handover_interval_s=12.0,
            handover_jitter_s=4.0,
        )
        self.assertTrue(has_honesty_label(law))
        # Mix without needing a second warn once labeled; leo/from_csv
        # paths with honesty label stay quiet.
        self.assertIsNone(sim_ne_orbit_warning(law))

    def test_orbit_claim_name_warns(self):
        src = _prog(
            """
path OrbitCellReplay {
  handover ~ every 12s jitter 4s
}
"""
        )
        res = check(parse(src, "claim.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any(SIM_NE_ORBIT in w for w in res.warnings))
        self.assertTrue(any("orbit/cell replay" in w for w in res.warnings))
        self.assertIn(SIM_NE_ORBIT, res.path_bound)

    def test_from_csv_honesty_surface_no_load(self):
        # Recognized for honesty; does not wire CSV bytes (PR #48).
        law = parse_path_model(
            PathModel(name="LeoFastHO", fields={"from_csv": "missing.csv"})
        )
        self.assertFalse(law.errors)
        self.assertIn("from_csv", law.stamp())
        self.assertIn(SIM_NE_ORBIT, law.stamp())
        warn = sim_ne_orbit_warning(law)
        self.assertIsNotNone(warn)
        self.assertIn("from_csv", warn)

    def test_reach_cli_prints_sim_ne_orbit(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", str(EX / "reach.vela")])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn(SIM_NE_ORBIT, out)
        self.assertIn("Starlink-class", out)
        self.assertIn("path=LeoFastHO:leo_fast_ho", out)


if __name__ == "__main__":
    unittest.main()
