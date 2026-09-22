"""Seed-7 ablation helper: cheaper next HorizonChase attempt.

Default is a fast, fail-closed dry layout that does not claim DualGate.
Use --run to hit the sibling sim. HorizonChase stays off the flagship
until this script is green on seed 7 and seed 13 (see docs/EVAL-NOTES.md).

gate is stamped from the rails that ran. --fast / 45s is not the house
gate. power=low for n<8. Do not fork Detect/SoftReprobe.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vela.eval_harness import _import_sim, scenario_cfg
from vela.ir import VelaConfig
from vela.kernel import make_cca
from vela.receipt import eval_gate
from vela.types import power_label_for_seeds


VARIANTS = {
    "leoaware": "LeoAware",
    "pass": "Horizon-pass",
    "full": "Horizon-full",
    "chase": "Horizon-chase",
}


def _configs() -> dict[str, VelaConfig | None]:
    off = VelaConfig(
        predictive_freeze=False,
        interval_bw=False,
        horizon_chase=False,
        dual_gate_guard=False,
        typed_loss=False,
    )
    full = VelaConfig(horizon_chase=False)
    chase = VelaConfig(
        predictive_freeze=False,
        interval_bw=False,
        dual_gate_guard=False,
        horizon_chase=True,
    )
    return {
        "leoaware": None,  # sibling LeoAwareCCA
        "pass": off,
        "full": full,
        "chase": chase,
    }


def run_one(mod, name: str, factory, seed: int, duration: float) -> dict:
    scfg, n = scenario_cfg(mod, "leo_fast_ho", seed, duration)
    res = mod["run_sim"](factory, cfg=scfg, n_flows=n, path_hint_mode="none")
    m = mod["summarize_result"](res)[0]
    row = {
        "name": name,
        "seed": seed,
        "duration_s": duration,
        "goodput_mbps": m.goodput_bps / 1e6,
        "p95_rtt_ms": m.p95_rtt_s * 1000.0,
        "avg_rtt_ms": m.avg_rtt_s * 1000.0,
        "loss_rate": m.loss_rate,
    }
    print(
        f"{name:18} gp={row['goodput_mbps']:6.2f}  p95={row['p95_rtt_ms']:6.1f}  "
        f"avg={row['avg_rtt_ms']:5.1f}  loss={row['loss_rate']*100:.2f}%",
        flush=True,
    )
    return row


def build_plan(args: argparse.Namespace) -> dict:
    seeds = list(args.seeds)
    power = power_label_for_seeds(seeds)
    gate = eval_gate(seeds, args.duration, ["leo_fast_ho", "terrestrial"])
    wanted = list(args.only) if args.only else list(VARIANTS)
    for key in wanted:
        if key not in VARIANTS:
            raise SystemExit(f"unknown variant {key!r}; choose from {sorted(VARIANTS)}")
    return {
        "event": "ablate_seed7_plan",
        "variants": wanted,
        "seeds": seeds,
        "duration_s": args.duration,
        "gate": gate,
        "power": power,
        "honesty": (
            "Not a house DualGate claim. HorizonChase stays closed-write until "
            "seed 7 and seed 13 are green. SoftReprobe cut 0.58 on hop and "
            "flicker. " + power["note"]
        ),
        "run": bool(args.run),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--only",
        nargs="+",
        choices=sorted(VARIANTS),
        help="subset of variants (default: all). Prefer --only pass chase for a cheap chase check.",
    )
    ap.add_argument("--seeds", nargs="+", type=int, default=[7], help="seeds (default: 7)")
    ap.add_argument("--duration", type=float, default=45.0, help="seconds (default: 45)")
    ap.add_argument(
        "--run",
        action="store_true",
        help="execute against the LeoAware sibling sim (default: plan-only)",
    )
    ap.add_argument("--json-out", type=Path, help="write plan/results JSON")
    args = ap.parse_args(argv)

    plan = build_plan(args)
    print(
        f"ablate_seed7 gate={plan['gate']} power={plan['power']['power']} "
        f"variants={plan['variants']} seeds={plan['seeds']} "
        f"duration={plan['duration_s']:g}s",
        flush=True,
    )
    print(plan["honesty"], flush=True)

    results: list[dict] = []
    if args.run:
        try:
            mod = _import_sim()
        except Exception as exc:  # noqa: BLE001 - surface missing sibling clearly
            print(f"error: sibling sim unavailable: {exc}", flush=True)
            return 2
        cfgs = _configs()
        for key in plan["variants"]:
            label = VARIANTS[key]
            cfg = cfgs[key]
            for seed in plan["seeds"]:
                if cfg is None:
                    factory = lambda: mod["LeoAwareCCA"]()
                else:
                    factory = make_cca(cfg)
                results.append(
                    run_one(mod, label, factory, seed, plan["duration_s"])
                )
    else:
        print(
            "plan-only (no sim). Re-run with --run when leo-aware-transport is present.",
            flush=True,
        )

    payload = {**plan, "results": results}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
