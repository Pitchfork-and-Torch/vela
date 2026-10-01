"""Observe-only Reach passthrough rails. Not a dual-gate claim."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from vela.checker import check
from vela.compile import compile_source
from vela.eval_harness import (
    LEO_S7_45_GP,
    LEO_S7_45_P95,
    passthrough_ok,
)
from vela.parser import parse

ROOT = Path(__file__).resolve().parents[1]
CLOSED = (
    "HorizonChase",
    "TrimFill",
    "TrimReclaim",
    "QuietReach",
    "QuietShield",
    "SoftFlicker",
    "TrimHold",
)


class TestPassthroughRails(unittest.TestCase):
    def test_match_on_locked_seed7(self):
        leo = {"goodput_mbps": LEO_S7_45_GP, "p95_rtt_ms": LEO_S7_45_P95}
        reach = {"goodput_mbps": 88.65237333333333, "p95_rtt_ms": 108.40870991576682}
        self.assertTrue(passthrough_ok(leo, reach))

    def test_miss_when_goodput_drifts(self):
        leo = {"goodput_mbps": LEO_S7_45_GP, "p95_rtt_ms": LEO_S7_45_P95}
        reach = {"goodput_mbps": 88.50, "p95_rtt_ms": LEO_S7_45_P95}
        self.assertFalse(passthrough_ok(leo, reach))

    def test_miss_when_p95_drifts(self):
        leo = {"goodput_mbps": LEO_S7_45_GP, "p95_rtt_ms": LEO_S7_45_P95}
        reach = {"goodput_mbps": LEO_S7_45_GP, "p95_rtt_ms": 108.7}
        self.assertFalse(passthrough_ok(leo, reach))

    def test_miss_when_leo_is_not_the_locked_rail(self):
        leo = {"goodput_mbps": 80.0, "p95_rtt_ms": LEO_S7_45_P95}
        reach = {"goodput_mbps": 80.0, "p95_rtt_ms": LEO_S7_45_P95}
        self.assertFalse(passthrough_ok(leo, reach))

    def test_reach_compose_is_observe_only(self):
        src = (ROOT / "examples" / "reach.vela").read_text(encoding="utf-8")
        prog = parse(src, "reach.vela")
        for name in CLOSED:
            self.assertNotIn(name, prog.controllers[0].compose)
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        _text, cfg = compile_source(src, "reach.vela")
        self.assertFalse(cfg.horizon_chase)
        self.assertFalse(cfg.trim_fill)
        self.assertFalse(cfg.trim_reclaim)
        self.assertFalse(cfg.quiet_reach)
        self.assertFalse(cfg.quiet_shield)
        self.assertFalse(cfg.soft_flicker)
        self.assertFalse(cfg.trim_hold)

    def test_results_json_is_match_not_dual_gate(self):
        path = ROOT / "results" / "eval_reach-passthrough.json"
        if not path.is_file():
            self.skipTest("no local eval_reach-passthrough.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["verdict"], "MATCH")
        self.assertFalse(data["dual_gate"])
        self.assertTrue(passthrough_ok(data["leo"], data["reach"]))


if __name__ == "__main__":
    unittest.main()
