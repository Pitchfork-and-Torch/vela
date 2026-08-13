"""VELA 0.3 Equinox laws: integrator, kinds, caps, receipts."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from vela.checker import check
from vela.digest import compose_digest, merkle, source_digest, stdlib_catalog, tagged
from vela.parser import parse
from vela.receipt import build_receipt, verify_receipt

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


class TestEquinox(unittest.TestCase):
    def test_equinox_checks(self):
        src = (EX / "equinox.vela").read_text(encoding="utf-8")
        prog = parse(src, "equinox.vela")
        self.assertEqual(prog.version, "0.3")
        self.assertEqual(prog.controllers[0].authority.get("cwnd"), 0)
        self.assertEqual(prog.views[0].name, "Observe")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(res.compose_digest)
        self.assertIn("Observe", res.views)

    def test_integrator_rejected(self):
        src = """
lang vela 0.3
controller Bad {
  compose Detect
  signals:
    epoch: Epoch
  when p_ho > 0.35 {
    pace *= 0.94
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "bad.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("integrator" in e for e in res.errors))

    def test_integrate_when_opts_in(self):
        src = """
lang vela 0.3
controller Risky {
  compose Detect
  signals:
    epoch: Epoch
  integrate when p_ho > 0.35 {
    pace *= 0.94
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "risky.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertTrue(any("integrate when" in w for w in res.warnings))

    def test_reconfig_match_must_be_closed(self):
        src = """
lang vela 0.3
controller Bad {
  compose Detect + SoftReprobe
  signals:
    epoch: Epoch
    rtt: Sample<ms> @ epoch
  on Reconfig(e) match e {
    RttHop => hold
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "bad-re.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("Flicker" in e for e in res.errors))

    def test_cut_refinement(self):
        src = """
lang vela 0.3
controller Bad {
  compose Detect
  signals:
    epoch: Epoch
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(1.2)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "bad-cut.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("cut(1.2)" in e for e in res.errors))

    def test_writecap_blocks_ambient_write(self):
        src = """
lang vela 0.3
controller Bad {
  compose Detect
  authority { cwnd: 0, pace: 0 }
  signals:
    epoch: Epoch
    cap: WriteCap<cwnd> @ epoch
  when p_ho > 0.5 {
    pace = bw
  }
  on Loss(k) match k {
    Mobility => hold
    Congestive => cut(0.7)
    Unknown => hold
  }
}
"""
        res = check(parse(src, "bad-cap.vela"))
        self.assertFalse(res.ok)
        self.assertTrue(any("WriteCap" in e for e in res.errors))

    def test_existing_examples_still_check(self):
        for name in ("horizon.vela", "reach.vela", "luff.vela", "leoaware_oce.vela"):
            src = (EX / name).read_text(encoding="utf-8")
            res = check(parse(src, name))
            self.assertTrue(res.ok, (name, res.errors))

    def test_digest_stable_and_domain_separated(self):
        a = tagged("src", "hello")
        b = tagged("mech", "hello")
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), 64)
        cat = stdlib_catalog()
        self.assertIn("Detect", cat)
        self.assertEqual(cat["Detect"], cat["Detect"])
        d1 = compose_digest(["Detect", "SoftReprobe"])
        d2 = compose_digest(["Detect", "SoftReprobe"])
        d3 = compose_digest(["SoftReprobe", "Detect"])
        self.assertEqual(d1, d2)
        self.assertNotEqual(d1, d3)

    def test_receipt_roundtrip(self):
        src = (EX / "equinox.vela").read_text(encoding="utf-8")
        summary = {
            "verdict": "FAIL",
            "power": "low",
            "honesty": "test",
            "rows": [
                {
                    "scenario": "leo_fast_ho",
                    "seed": 7,
                    "cca": "Equinox",
                    "goodput_mbps": 88.65,
                    "p95_rtt_ms": 108.4,
                }
            ],
        }
        rec = build_receipt(
            source=src,
            source_name="equinox.vela",
            compose=["Detect", "SoftReprobe"],
            config={"name": "Equinox"},
            summary=summary,
        )
        self.assertEqual(verify_receipt(rec, source=src), [])
        rec["verdict"] = "ACCEPT"
        self.assertTrue(verify_receipt(rec, source=src))

    def test_source_digest_binds_text(self):
        self.assertNotEqual(source_digest("a"), source_digest("b"))
        self.assertEqual(merkle([]), merkle([]))
        self.assertNotEqual(merkle(["aa"]), merkle(["bb"]))


if __name__ == "__main__":
    unittest.main()
