"""Seed-7 45s ablation: LeoAware vs Horizon passthrough vs full."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vela.eval_harness import _import_sim, scenario_cfg
from vela.ir import VelaConfig
from vela.kernel import make_cca


def run(mod, name, factory, seed=7, duration=45.0):
    scfg, n = scenario_cfg(mod, "leo_fast_ho", seed, duration)
    res = mod["run_sim"](factory, cfg=scfg, n_flows=n, path_hint_mode="none")
    m = mod["summarize_result"](res)[0]
    print(
        f"{name:18} gp={m.goodput_bps/1e6:6.2f}  p95={m.p95_rtt_s*1000:6.1f}  "
        f"avg={m.avg_rtt_s*1000:5.1f}  loss={m.loss_rate*100:.2f}%",
        flush=True,
    )


def main() -> None:
    mod = _import_sim()
    off = VelaConfig(
        predictive_freeze=False,
        interval_bw=False,
        horizon_chase=False,
        dual_gate_guard=False,
        typed_loss=False,
    )
    full = VelaConfig()
    run(mod, "LeoAware", lambda: mod["LeoAwareCCA"]())
    run(mod, "Horizon-pass", make_cca(off))
    run(mod, "Horizon-full", make_cca(full))
    run(mod, "Horizon-chase", make_cca(VelaConfig(predictive_freeze=False, interval_bw=False, dual_gate_guard=False)))
    run(mod, "Horizon-s13", make_cca(full), seed=13)


if __name__ == "__main__":
    main()
