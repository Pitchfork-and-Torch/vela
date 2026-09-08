"""Ablate Reach vs LeoAware on the seeds that killed Horizon and Luff."""
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
    full = program_to_config(parse(src, "reach.vela"))
    variants = {
        "LeoAware": VelaConfig(name="LeoAware"),
        "flicker": VelaConfig(
            name="Reach",
            soft_flicker=True,
            quiet_shield=False,
            quiet_reach=False,
            trim_hold=False,
        ),
        "reach": full,
    }
    jobs = [
        ("leo_fast_ho", 7, 45.0),
        ("leo_fast_ho", 7, 90.0),
        ("leo_fast_ho", 123, 90.0),
        ("leo_fast_ho", 13, 90.0),
        ("terrestrial", 13, 45.0),
    ]
    for scen, seed, dur in jobs:
        for name, cfg in variants.items():
            algo = "LeoAware" if name == "LeoAware" else "Reach"
            print(f"{scen} seed={seed} {dur:.0f}s {name} ...", flush=True)
            rec = run_one_isolated(algo, scen, seed, dur, cfg)
            print(
                f"  gp={rec['goodput_mbps']:.2f} p95={rec['p95_rtt_ms']:.1f}",
                flush=True,
            )


if __name__ == "__main__":
    main()
