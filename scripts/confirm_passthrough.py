"""Confirm observe-only Reach matches LeoAware on seed 7 45s."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vela.eval_harness import run_one_isolated
from vela.ir import VelaConfig, program_to_config
from vela.parser import parse


def main() -> None:
    src = (ROOT / "examples" / "reach.vela").read_text(encoding="utf-8")
    cfg = program_to_config(parse(src, "reach.vela"))
    for name, c, algo in (
        ("LeoAware", VelaConfig(name="LeoAware"), "LeoAware"),
        ("Reach", cfg, "Reach"),
    ):
        rec = run_one_isolated(algo, "leo_fast_ho", 7, 45.0, c)
        print(f"{name} {rec['goodput_mbps']:.2f}/{rec['p95_rtt_ms']:.1f}", flush=True)


if __name__ == "__main__":
    main()
