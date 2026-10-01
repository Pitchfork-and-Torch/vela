"""Split Luff levers on seed 7 45s."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vela.eval_harness import run_one_isolated
from vela.ir import VelaConfig


def main() -> None:
    variants = {
        "LeoAware": VelaConfig(name="LeoAware"),
        "hold": VelaConfig(
            name="Luff",
            trim_hold=True,
            trim_fill=False,
            trim_reclaim=False,
            interval_bw=True,
        ),
        "fill": VelaConfig(
            name="Luff",
            trim_hold=False,
            trim_fill=True,
            trim_reclaim=False,
            interval_bw=True,
        ),
        "both": VelaConfig(
            name="Luff",
            trim_hold=True,
            trim_fill=True,
            trim_reclaim=False,
            interval_bw=True,
        ),
    }
    for name, cfg in variants.items():
        print(f"seed7 45s {name} ...", flush=True)
        rec = run_one_isolated(
            "LeoAware" if name == "LeoAware" else "Luff",
            "leo_fast_ho",
            7,
            45.0,
            cfg,
        )
        print(f"  gp={rec['goodput_mbps']:.2f} p95={rec['p95_rtt_ms']:.1f}", flush=True)


if __name__ == "__main__":
    main()
