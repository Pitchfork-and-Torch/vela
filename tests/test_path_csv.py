"""from_csv path law: real CSV traces bind into PathModel."""
from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from vela.ast import PathModel
from vela.checker import check
from vela.cli import main
from vela.ir import program_to_config
from vela.parser import parse
from vela.path import (
    load_path_csv,
    parse_path_model,
    path_digest,
    path_csv_capacity_error,
    path_csv_headers_error,
    path_csv_missing_error,
    path_csv_mix_error,
    path_csv_time_error,
    path_trace_csv,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "starlink_tiny.csv"
EX = ROOT / "examples"


def _prog(path_body: str) -> str:
    return f"""
lang vela 0.1
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


class TestPathCsv(unittest.TestCase):
    def test_fixture_loads(self):
        digest, n_rows, n_ho, errs = load_path_csv(FIXTURE, name="T")
        self.assertEqual(errs, [])
        self.assertEqual(n_rows, 11)
        self.assertEqual(n_ho, 2)
        raw = FIXTURE.read_bytes()
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_parse_from_csv_binds(self):
        law = parse_path_model(
            PathModel(name="LeoFastHO", fields={"from_csv": str(FIXTURE)})
        )
        self.assertEqual(law.errors, [])
        self.assertTrue(law.bound)
        self.assertFalse(law.house)
        self.assertEqual(law.scenario, "leo_fast_ho")
        self.assertTrue(law.csv_sha256)
        self.assertIn("from_csv", law.stamp())
        d = path_digest([law])
        self.assertTrue(d)
        # Content hash is inside the tagged blob; digest commits it.
        self.assertNotEqual(d, path_digest([]))
        self.assertEqual(law.as_dict()["csv_sha256"], law.csv_sha256)

    def test_check_program_with_fixture(self):
        src = _prog(
            f'''
path LeoFastHO {{
  from_csv ~ "{FIXTURE.as_posix()}"
}}
'''
        )
        prog = parse(src, "csv_ok.vela")
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        self.assertIn("from_csv", res.path_bound)
        cfg = program_to_config(prog)
        self.assertTrue(cfg.trace_csv)
        self.assertEqual(Path(cfg.trace_csv).resolve(), FIXTURE.resolve())
        self.assertEqual(cfg.paths[0]["csv_sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())
        self.assertTrue(cfg.path_digest)
        self.assertEqual(
            path_trace_csv("leo_fast_ho", cfg),
            str(Path(cfg.trace_csv)),
        )

    def test_relative_from_source_dir(self):
        src = _prog(
            """
path LeoFastHO {
  from_csv ~ "tests/fixtures/starlink_tiny.csv"
}
"""
        )
        prog = parse(src, str(ROOT / "examples" / "csv_rel.vela"))
        res = check(prog)
        self.assertTrue(res.ok, res.errors)
        cfg = program_to_config(prog)
        self.assertEqual(Path(cfg.trace_csv).resolve(), FIXTURE.resolve())

    def test_missing_file_fail_closed(self):
        missing = (ROOT / "missing_trace.csv").resolve()
        law = parse_path_model(
            PathModel(name="LeoFastHO", fields={"from_csv": "missing_trace.csv"}),
            base_dir=ROOT,
        )
        self.assertFalse(law.bound)
        self.assertIn(path_csv_missing_error("LeoFastHO", str(missing)), law.errors)

    def test_bad_headers_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.csv"
            bad.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
            digest, n, h, errs = load_path_csv(bad, name="T")
            self.assertTrue(digest)
            self.assertEqual(n, 0)
            self.assertIn(path_csv_headers_error("T", str(bad), "a,b,c"), errs)

    def test_non_positive_capacity_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "cap.csv"
            bad.write_text(
                "t_s,rtt_ms,capacity_mbps,loss_p,reconfig\n"
                "0.0,35.0,0.0,0.0,0\n",
                encoding="utf-8",
            )
            _, _, _, errs = load_path_csv(bad, name="T")
            self.assertIn(path_csv_capacity_error("T", str(bad), 2, 0.0), errs)

    def test_inverted_time_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "time.csv"
            bad.write_text(
                "t_s,rtt_ms,capacity_mbps,loss_p,reconfig\n"
                "0.0,35.0,80.0,0.0,0\n"
                "1.0,35.0,80.0,0.0,0\n"
                "0.5,35.0,80.0,0.0,0\n",
                encoding="utf-8",
            )
            _, _, _, errs = load_path_csv(bad, name="T")
            self.assertIn(path_csv_time_error("T", str(bad), 4, 1.0, 0.5), errs)

    def test_mix_parametric_and_csv_fail_closed(self):
        src = _prog(
            f'''
path LeoFastHO {{
  handover ~ every 12s jitter 4s
  from_csv ~ "{FIXTURE.as_posix()}"
}}
'''
        )
        res = check(parse(src, "mix.vela"))
        self.assertFalse(res.ok)
        self.assertIn(path_csv_mix_error("LeoFastHO"), res.errors)

    def test_leo_fast_ho_parametric_still_works(self):
        src = (EX / "reach.vela").read_text(encoding="utf-8")
        res = check(parse(src, "reach.vela"))
        self.assertTrue(res.ok, res.errors)
        self.assertIn("house", res.path_bound)
        self.assertNotIn("from_csv", res.path_bound)

    def test_digest_changes_with_csv_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.csv"
            b = Path(td) / "b.csv"
            hdr = "t_s,rtt_ms,capacity_mbps,loss_p,reconfig\n"
            a.write_text(hdr + "0.0,35.0,80.0,0.0,0\n", encoding="utf-8")
            b.write_text(hdr + "0.0,35.0,81.0,0.0,0\n", encoding="utf-8")
            la = parse_path_model(
                PathModel(name="LeoFastHO", fields={"from_csv": str(a)})
            )
            lb = parse_path_model(
                PathModel(name="LeoFastHO", fields={"from_csv": str(b)})
            )
            self.assertNotEqual(la.csv_sha256, lb.csv_sha256)
            self.assertNotEqual(path_digest([la]), path_digest([lb]))

    def test_example_starlink_csv_checks(self):
        path = EX / "starlink_csv.vela"
        if not path.is_file():
            self.skipTest("example not present")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["check", str(path)])
        self.assertEqual(rc, 0, buf.getvalue())
        out = buf.getvalue()
        self.assertIn("from_csv", out)
        self.assertIn("observe-only", out)


if __name__ == "__main__":
    unittest.main()
