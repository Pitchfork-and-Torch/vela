"""Seed-7 ablation helper: cheaper next HorizonChase gift-to-LeoAware.

Fail-closed by default (--dry-run / plan-only). SoftReprobe cut stays
0.58 on hop and flicker. SoftFlicker and QuietShield are refused on
observe. HorizonChase stays closed-write until seeds 7 and 13 are both
green (see docs/EVAL-NOTES.md seed-7 ablation table).

Clear labels: hop = real handover (RttHop); flicker = mid-epoch
capacity wobble / counterfeit REPROBE extras (not a hop bug).

gate is stamped from the rails that ran. 45s / subset of {13,7} is
gate=fast, not the house DualGate. Do not fork Detect/SoftReprobe.
No dish Mbps claims. No closed-write enable from this script.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vela.eval_harness import _import_sim, scenario_cfg
from vela.ir import VelaConfig
from vela.kernel import leo_aware_root, make_cca
from vela.receipt import eval_gate
from vela.types import HOUSE_ENDPOINT_CUT, POWER_OK_MIN_SEEDS, eval_power


# Required green before any HorizonChase compose change (EVAL-NOTES).
REQUIRED_GREEN_SEEDS: tuple[int, ...] = (7, 13)

# SoftFlicker / QuietShield: closed on observe (fail-closed gift path).
REFUSED_ON_OBSERVE: frozenset[str] = frozenset({"SoftFlicker", "QuietShield"})

VARIANTS = {
    "leoaware": "LeoAware",
    "pass": "Horizon-pass",
    "full": "Horizon-full",
    "chase": "Horizon-chase",
}

HOP_FLICKER_LABELS = {
    "hop": "RttHop / real handover (SoftReprobe cut 0.58)",
    "flicker": (
        "mid-epoch capacity wobble; detect-HO extras are flicker-class, "
        "not hop bugs (SoftReprobe still 0.58; SoftFlicker is review)"
    ),
}


def refuse_closed_on_observe(cfg: VelaConfig) -> None:
    """Fail-closed: SoftFlicker / QuietShield must not ride observe."""
    mechs = set(cfg.mechanisms or [])
    flagged = []
    if cfg.soft_flicker or "SoftFlicker" in mechs:
        flagged.append("SoftFlicker")
    if cfg.quiet_shield or "QuietShield" in mechs:
        flagged.append("QuietShield")
    if not flagged:
        return
    # Observe posture or observe_only: refuse. Review/closed-write class
    # may name them elsewhere; this gift path never enables them.
    if cfg.observe_only or getattr(cfg, "posture", "observe") == "observe":
        names = ", ".join(flagged)
        raise SystemExit(
            f"refuse: {names} not allowed on observe "
            f"(SoftReprobe cut stays {HOUSE_ENDPOINT_CUT}; "
            "SoftFlicker/QuietShield are review / closed-write class)"
        )


def assert_gift_configs_safe(cfgs: dict[str, VelaConfig | None]) -> None:
    """Every VELA variant on this gift path must pass refuse_closed_on_observe."""
    for key, cfg in cfgs.items():
        if cfg is None:
            continue
        refuse_closed_on_observe(cfg)
        # Chase is named for ablation but must not silently enable SoftFlicker.
        if cfg.soft_flicker or cfg.quiet_shield:
            raise SystemExit(
                f"refuse: variant {key!r} enables SoftFlicker/QuietShield "
                f"(cut must stay {HOUSE_ENDPOINT_CUT})"
            )


def _configs() -> dict[str, VelaConfig | None]:
    # Passthrough / observe gift: no SoftFlicker, no QuietShield.
    off = VelaConfig(
        predictive_freeze=False,
        interval_bw=False,
        horizon_chase=False,
        dual_gate_guard=False,
        typed_loss=False,
        soft_flicker=False,
        quiet_shield=False,
        observe_only=True,
        posture="observe",
    )
    # "full" here means Horizon compose WITHOUT chase (EVAL-NOTES decision).
    full = VelaConfig(
        horizon_chase=False,
        soft_flicker=False,
        quiet_shield=False,
        observe_only=True,
        posture="observe",
    )
    # Chase is the closed-write candidate under test; still no SoftFlicker.
    chase = VelaConfig(
        predictive_freeze=False,
        interval_bw=False,
        dual_gate_guard=False,
        horizon_chase=True,
        soft_flicker=False,
        quiet_shield=False,
        observe_only=False,
        posture="review",
    )
    return {
        "leoaware": None,  # sibling LeoAwareCCA
        "pass": off,
        "full": full,
        "chase": chase,
    }


def green_seed_gate(seeds: list[int]) -> dict[str, Any]:
    """Document required green seeds 7+13 before any compose change."""
    have = set(int(s) for s in seeds)
    need = set(REQUIRED_GREEN_SEEDS)
    missing = sorted(need - have)
    return {
        "required_green_seeds": list(REQUIRED_GREEN_SEEDS),
        "seeds_in_plan": sorted(have),
        "missing_required": missing,
        "compose_change_allowed": not missing and need <= have,
        "note": (
            "HorizonChase stays closed-write until ablate_seed7 is green on "
            "seed 7 and seed 13. Do not change compose until both are green."
        ),
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
        "arm_labels": dict(HOP_FLICKER_LABELS),
        "soft_reprobe_cut": HOUSE_ENDPOINT_CUT,
    }
    print(
        f"{name:18} seed={seed} gp={row['goodput_mbps']:6.2f}  "
        f"p95={row['p95_rtt_ms']:6.1f}  avg={row['avg_rtt_ms']:5.1f}  "
        f"loss={row['loss_rate']*100:.2f}%",
        flush=True,
    )
    return row


def build_plan(args: argparse.Namespace) -> dict:
    seeds = [int(s) for s in args.seeds]
    power = eval_power(len(seeds))
    # Stamp gate from leo_fast_ho only unless terrestrial also planned.
    scenarios = ["leo_fast_ho"]
    if args.with_terrestrial:
        scenarios.append("terrestrial")
    gate = eval_gate(seeds, args.duration, scenarios)
    wanted = list(args.only) if args.only else list(VARIANTS)
    for key in wanted:
        if key not in VARIANTS:
            raise SystemExit(f"unknown variant {key!r}; choose from {sorted(VARIANTS)}")
    green = green_seed_gate(seeds)
    dry = bool(args.dry_run) or not bool(args.run)
    return {
        "event": "ablate_seed7_plan",
        "variants": wanted,
        "seeds": seeds,
        "duration_s": float(args.duration),
        "scenarios": scenarios,
        "gate": gate,
        "power": power,
        "power_note": (
            f"power={power} (n={len(seeds)}; power=low when "
            f"n<{POWER_OK_MIN_SEEDS}). Not a DualGate claim."
        ),
        "soft_reprobe_cut": HOUSE_ENDPOINT_CUT,
        "hop_vs_flicker": dict(HOP_FLICKER_LABELS),
        "refused_on_observe": sorted(REFUSED_ON_OBSERVE),
        "green_seeds": green,
        "dry_run": dry,
        "run": bool(args.run) and not bool(args.dry_run),
        "honesty": (
            "Not a house DualGate claim. SoftReprobe cut "
            f"{HOUSE_ENDPOINT_CUT} on hop and flicker. SoftFlicker and "
            "QuietShield refused on observe. HorizonChase stays closed-write "
            "until seed 7 and seed 13 are green. Hop = RttHop / real HO; "
            "flicker = mid-epoch wobble (detect-HO extras), not a hop bug."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--only",
        nargs="+",
        choices=sorted(VARIANTS),
        help="subset of variants (default: all). Prefer --only pass chase.",
    )
    ap.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=[7, 13],
        help="seeds (default: 7 13 - both required green before compose change)",
    )
    ap.add_argument("--duration", type=float, default=45.0, help="seconds (default: 45)")
    ap.add_argument(
        "--with-terrestrial",
        action="store_true",
        help="include terrestrial in gate stamp (still not house DualGate alone)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="plan-only: print honesty + plan JSON fields, no sim (default if no --run)",
    )
    ap.add_argument(
        "--run",
        action="store_true",
        help="execute against the LeoAware sibling sim (requires sibling present)",
    )
    ap.add_argument("--json-out", type=Path, help="write plan/results JSON")
    args = ap.parse_args(argv)

    if args.run and args.dry_run:
        print("error: pass only one of --run / --dry-run", flush=True)
        return 2

    plan = build_plan(args)
    print(
        f"ablate_seed7 gate={plan['gate']} power={plan['power']} "
        f"variants={plan['variants']} seeds={plan['seeds']} "
        f"duration={plan['duration_s']:g}s dry_run={plan['dry_run']}",
        flush=True,
    )
    print(plan["honesty"], flush=True)
    print(
        f"hop: {HOP_FLICKER_LABELS['hop']}\n"
        f"flicker: {HOP_FLICKER_LABELS['flicker']}",
        flush=True,
    )
    print(
        f"refused_on_observe={plan['refused_on_observe']} "
        f"soft_reprobe_cut={HOUSE_ENDPOINT_CUT}",
        flush=True,
    )
    green = plan["green_seeds"]
    print(
        f"required_green_seeds={green['required_green_seeds']} "
        f"missing={green['missing_required']} "
        f"compose_change_allowed={green['compose_change_allowed']}",
        flush=True,
    )
    if green["missing_required"]:
        print(
            "WARN: plan is missing required green seeds; "
            "do not change compose / re-enable HorizonChase yet.",
            flush=True,
        )

    # Fail-closed config check even on dry-run (cheap).
    cfgs = _configs()
    try:
        assert_gift_configs_safe(cfgs)
    except SystemExit as exc:
        print(str(exc), flush=True)
        return 2

    results: list[dict] = []
    if plan["run"]:
        root = leo_aware_root()
        if not (root / "leo_cc").is_dir():
            print(f"error: LeoAware sibling missing at {root}", flush=True)
            return 2
        try:
            mod = _import_sim()
        except Exception as exc:  # noqa: BLE001 - surface missing sibling clearly
            print(f"error: sibling sim unavailable: {exc}", flush=True)
            return 2
        print(f"LeoAware root={root}", flush=True)
        for key in plan["variants"]:
            label = VARIANTS[key]
            cfg = cfgs[key]
            if cfg is not None:
                refuse_closed_on_observe(cfg)
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
            "dry-run / plan-only (no sim). Re-run with --run when "
            "leo-aware-transport is present. SoftFlicker/QuietShield stay refused.",
            flush=True,
        )

    payload = {**plan, "results": results}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.json_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
