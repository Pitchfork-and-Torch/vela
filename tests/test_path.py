"""Path law: declared model binds check, compile, eval, and receipt."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.checker import check
from vela.cli import main
from vela.compile import compile_source
from vela.eval_harness import scenario_cfg
from vela.ir import program_to_config
from vela.parser import parse
from vela.path import (
    HOUSE_CAPACITY_HI_BPS,
    HOUSE_CAPACITY_LO_BPS,
    HOUSE_HANDOVER_INTERVAL_S,
    HOUSE_HANDOVER_JITTER_S,
    HOUSE_MOBILITY_P,
    HOUSE_MOBILITY_WINDOW_S,
    HOUSE_RTT_JUMP_HI_S,
    HOUSE_RTT_JUMP_LO_S,
    path_digest,
    path_needs_std_error,
    path_overlay,
    path_parse_error,
    path_unknown_field_error,
)
from vela.receipt import build_receipt, verify_receipt

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def _prog(uses: str, path_body: str | None = None) -> str:
    block = path_body if path_body is not None else """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
"""
    return f"""
lang vela 0.1
{uses}
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
{block}
"""


class FakePath:
    def __init__(self, **kw):
        self.kw = kw


class TestPathBind(unittest.TestCase):
    def test_flagship_examples_bind_house_leofastho(self):
        for name in (
            "reach.vela",
            "equinox.vela",
            "fair.vela",
            "horizon.vela",
            "ascent.vela",
            "luff.vela",
        ):
            src = (EX / name).read_text(encoding="utf-8")
            prog = parse(src, name)
            res = check(prog)
            self.assertTrue(res.ok, (name, res.errors))
            self.assertIn("LeoFastHO:leo_fast_ho", res.path_bound)
            self.assertIn("house", res.path_bound)
            self.assertTrue(res.path_digest)
            cfg = program_to_config(prog)
            self.assertEqual(cfg.path_name, "LeoFastHO")
            self.assertEqual(cfg.path_scenario, "leo_fast_ho")
            self.assertEqual(cfg.handover_interval_s, HOUSE_HANDOVER_INTERVAL_S)
            self.assertEqual(cfg.handover_jitter_s, HOUSE_HANDOVER_JITTER_S)

    def test_reach_check_cli_prints_path(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", str(EX / "reach.vela")])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("path=LeoFastHO:leo_fast_ho", out)
        self.assertIn("house", out)
        self.assertIn("affine", out)
        self.assertIn("hybrid", out)

    def test_path_requires_std_path(self):
        res = check(parse(_prog(""), "nopath.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_needs_std_error(), res.errors)

    def test_unknown_field_is_type_error(self):
        src = _prog(
            "use std.path",
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  next_hop ~ 3s
}
""",
        )
        res = check(parse(src, "bad-field.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_unknown_field_error("LeoFastHO", "next_hop"), res.errors)

    def test_unparseable_handover_is_type_error(self):
        src = _prog(
            "use std.path",
            """
path LeoFastHO {
  handover ~ soon
}
""",
        )
        res = check(parse(src, "bad-ho.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_parse_error("LeoFastHO", "handover"), res.errors)

    def test_empty_path_is_type_error(self):
        src = _prog("use std.path", "path LeoFastHO { }\n")
        res = check(parse(src, "empty.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("empty model" in e for e in res.errors))

    def test_unbound_name_warns(self):
        src = _prog(
            "use std.path",
            """
path WeatherCell {
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
""",
        )
        res = check(parse(src, "unbound.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("does not bind a known scenario" in w for w in res.warnings))
        cfg = program_to_config(parse(src, "unbound.vela"))
        self.assertEqual(cfg.path_name, "WeatherCell")
        self.assertEqual(cfg.path_scenario, "")
        self.assertIsNone(cfg.handover_interval_s)

    def test_house_mismatch_warns(self):
        src = _prog(
            "use std.path",
            """
path LeoFastHO {
  handover ~ every 1s jitter 0s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
""",
        )
        res = check(parse(src, "mismatch.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("not the house" in w for w in res.warnings))
        cfg = program_to_config(parse(src, "mismatch.vela"))
        self.assertEqual(cfg.handover_interval_s, 1.0)
        self.assertEqual(cfg.handover_jitter_s, 0.0)

    def test_scenario_cfg_uses_bound_rails(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        cfg = program_to_config(parse(src, "reach.vela"))
        mod = {"LeoPathConfig": FakePath}
        scfg, n = scenario_cfg(mod, "leo_fast_ho", 7, 45.0, cfg)
        self.assertEqual(n, 1)
        self.assertEqual(scfg.kw["handover_interval_s"], 12.0)
        self.assertEqual(scfg.kw["handover_jitter_s"], 4.0)
        self.assertEqual(scfg.kw["capacity_min_bps"], HOUSE_CAPACITY_LO_BPS)
        self.assertEqual(scfg.kw["capacity_max_bps"], HOUSE_CAPACITY_HI_BPS)
        self.assertEqual(scfg.kw["rtt_jump_min_s"], HOUSE_RTT_JUMP_LO_S)
        self.assertEqual(scfg.kw["rtt_jump_max_s"], HOUSE_RTT_JUMP_HI_S)
        self.assertEqual(scfg.kw["reconfig_loss_burst_p"], HOUSE_MOBILITY_P)
        self.assertEqual(scfg.kw["reconfig_loss_window_s"], HOUSE_MOBILITY_WINDOW_S)

    def test_scenario_cfg_without_path_keeps_house_defaults(self):
        mod = {"LeoPathConfig": FakePath}
        scfg, n = scenario_cfg(mod, "leo_fast_ho", 7, 45.0)
        self.assertEqual(n, 1)
        self.assertEqual(scfg.kw["handover_interval_s"], 12)
        self.assertEqual(scfg.kw["handover_jitter_s"], 4)

    def test_named_ablation_path_reaches_eval(self):
        src = _prog(
            "use std.path",
            """
path LeoFastHO {
  handover ~ every 8s jitter 2s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 20Mbps 120Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
""",
        )
        cfg = program_to_config(parse(src, "ablate.vela"))
        rails = path_overlay("leo_fast_ho", cfg)
        self.assertEqual(rails.handover_interval_s, 8.0)
        self.assertEqual(rails.handover_jitter_s, 2.0)
        self.assertEqual(rails.capacity_lo_bps, HOUSE_CAPACITY_LO_BPS)
        self.assertEqual(rails.capacity_hi_bps, HOUSE_CAPACITY_HI_BPS)
        other = path_overlay("leo_multi", cfg)
        self.assertIsNone(other.handover_interval_s)
        self.assertIsNone(other.handover_jitter_s)
        mod = {"LeoPathConfig": FakePath}
        scfg, _ = scenario_cfg(mod, "leo_fast_ho", 7, 45.0, cfg)
        self.assertEqual(scfg.kw["handover_interval_s"], 8.0)
        self.assertEqual(scfg.kw["handover_jitter_s"], 2.0)
        multi, n = scenario_cfg(mod, "leo_multi", 7, 45.0, cfg)
        self.assertEqual(n, 3)
        self.assertEqual(multi.kw["handover_interval_s"], 25)

    def test_compile_embeds_bound_path(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        text, cfg = compile_source(src, "reach.vela")
        self.assertEqual(cfg.path_name, "LeoFastHO")
        self.assertIn("path_name='LeoFastHO'", text)
        self.assertIn("handover_interval_s=12.0", text)

    def test_receipt_binds_path_digest(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        cfg = program_to_config(parse(src, "reach.vela"))
        rec = build_receipt(
            source=src,
            source_name="reach.vela",
            compose=list(cfg.mechanisms),
            config={
                "name": cfg.name,
                "paths": list(cfg.paths),
                "path_digest": cfg.path_digest,
            },
            summary={"verdict": "INCOMPLETE", "power": "low", "honesty": "test", "rows": []},
        )
        self.assertEqual(rec["path_digest"], cfg.path_digest)
        self.assertEqual(verify_receipt(rec, source=src), [])
        rec["path_digest"] = path_digest([])
        self.assertTrue(verify_receipt(rec, source=src))

    def test_inverted_capacity_is_not_a_rail(self):
        src = _prog(
            "use std.path",
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  capacity ~ uniform 120Mbps 20Mbps
}
""",
        )
        prog = parse(src, "inv-cap.vela")
        res = check(prog)
        self.assertFalse(res.ok)
        self.assertTrue(any("above high" in e and "capacity" in e for e in res.errors))
        cfg = program_to_config(prog)
        self.assertIsNone(cfg.capacity_lo_bps)
        self.assertIsNone(cfg.capacity_hi_bps)
        mod = {"LeoPathConfig": FakePath}
        scfg, _ = scenario_cfg(mod, "leo_fast_ho", 7, 45.0, cfg)
        self.assertNotIn("capacity_min_bps", scfg.kw)

    def test_jitter_wider_than_interval_is_not_a_cadence(self):
        src = _prog(
            "use std.path",
            """
path LeoFastHO {
  handover ~ every 2s jitter 5s
}
""",
        )
        res = check(parse(src, "wide-jit.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("not narrower" in e for e in res.errors))

    def test_zero_handover_interval_is_not_a_cadence(self):
        src = _prog(
            "use std.path",
            """
path LeoFastHO {
  handover ~ every 0s jitter 0s
}
""",
        )
        res = check(parse(src, "zero-ho.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("must be positive" in e for e in res.errors))

    def test_zero_capacity_and_zero_mobility_window(self):
        src = _prog(
            "use std.path",
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  capacity ~ uniform 0Mbps 10Mbps
  mobility_loss ~ burst p=0.08 window=0ms
}
""",
        )
        res = check(parse(src, "zero-geom.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("capacity" in e and "positive" in e for e in res.errors))
        self.assertTrue(any("mobility_loss window" in e for e in res.errors))

    def test_capacity_time_unit_names_the_mistake(self):
        src = _prog(
            "use std.path",
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  capacity ~ uniform 20ms 90ms
}
""",
        )
        res = check(parse(src, "cap-time.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("needs a rate" in e for e in res.errors))

    def test_off_house_capacity_binds_and_warns(self):
        src = _prog(
            "use std.path",
            """
path LeoFastHO {
  handover ~ every 12s jitter 4s
  rtt_jump ~ uniform 20ms 90ms
  capacity ~ uniform 40Mbps 80Mbps
  mobility_loss ~ burst p=0.08 window=400ms
}
""",
        )
        prog = parse(src, "narrow-cap.vela")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("not the house 20-120Mbps rail" in w for w in res.warnings))
        self.assertIn("named", res.path_bound)
        self.assertIn("cap 40-80Mbps", res.path_bound)
        cfg = program_to_config(prog)
        mod = {"LeoPathConfig": FakePath}
        scfg, _ = scenario_cfg(mod, "leo_fast_ho", 7, 45.0, cfg)
        self.assertEqual(scfg.kw["capacity_min_bps"], 40e6)
        self.assertEqual(scfg.kw["capacity_max_bps"], 80e6)
        self.assertEqual(scfg.kw["handover_interval_s"], 12.0)

    def test_house_geometry_matches_sim_defaults(self):
        root = Path.home() / "Projects" / "leo-aware-transport"
        if not (root / "leo_cc" / "network.py").is_file():
            self.skipTest("leo-aware-transport not present")
        import sys

        sys.path.insert(0, str(root))
        from leo_cc.network import LeoPathConfig

        bare = LeoPathConfig(
            duration_s=45.0,
            handover_interval_s=12.0,
            handover_jitter_s=4.0,
            seed=7,
        )
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        cfg = program_to_config(parse(src, "reach.vela"))
        scfg, _ = scenario_cfg({"LeoPathConfig": LeoPathConfig}, "leo_fast_ho", 7, 45.0, cfg)
        self.assertEqual(scfg.capacity_min_bps, bare.capacity_min_bps)
        self.assertEqual(scfg.capacity_max_bps, bare.capacity_max_bps)
        self.assertEqual(scfg.rtt_jump_min_s, bare.rtt_jump_min_s)
        self.assertEqual(scfg.rtt_jump_max_s, bare.rtt_jump_max_s)
        self.assertEqual(scfg.reconfig_loss_burst_p, bare.reconfig_loss_burst_p)
        self.assertEqual(scfg.reconfig_loss_window_s, bare.reconfig_loss_window_s)
        self.assertEqual(scfg.handover_interval_s, bare.handover_interval_s)
        self.assertEqual(scfg.handover_jitter_s, bare.handover_jitter_s)
        self.assertEqual(scfg.path_profile, bare.path_profile)

    def test_digest_ignores_absent_geometry_keys(self):
        old = {
            "name": "LeoFastHO",
            "scenario": "leo_fast_ho",
            "handover_interval_s": 12.0,
            "handover_jitter_s": 4.0,
            "fields": {"handover": "every 12s jitter 4s"},
        }
        newer = dict(old)
        newer["capacity_lo_bps"] = HOUSE_CAPACITY_LO_BPS
        newer["capacity_hi_bps"] = HOUSE_CAPACITY_HI_BPS
        self.assertEqual(path_digest([old]), path_digest([dict(old)]))
        self.assertNotEqual(path_digest([old]), path_digest([newer]))

    def test_compile_embeds_capacity_band(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        text, cfg = compile_source(src, "reach.vela")
        self.assertEqual(cfg.capacity_lo_bps, HOUSE_CAPACITY_LO_BPS)
        self.assertEqual(cfg.capacity_hi_bps, HOUSE_CAPACITY_HI_BPS)
        self.assertIn("capacity_lo_bps=20000000.0", text)
        self.assertIn("capacity_hi_bps=120000000.0", text)

    def test_oce_without_path_still_checks(self):
        src = (EX / "leoaware_oce.vela").read_text(encoding="utf-8")
        res = check(parse(src, "leoaware_oce.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertEqual(res.path_bound, "")


if __name__ == "__main__":
    unittest.main()
