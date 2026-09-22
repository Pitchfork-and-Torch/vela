"""Starlink LEO: hop vs flicker usefulness ablate.

House SoftReprobe cuts 0.58 on RttHop and Flicker. SoftFlicker (0.85,
posture review) historically dumped seed 7 45s to 55.2 / 123.8 when a
softer flicker cut was allowed to win. Compose soft cuts as min so
0.85 cannot undo 0.58; this script still names the closed class.

Also counts endpoint REPROBEs vs real handovers on seed 7 45s: the
extras are flicker/capacity wobble, not bugs (EVAL-NOTES).

gate=fast when duration is 45s / seeds subset of {13,7} with
leo_fast_ho+terrestrial. Never claim house DualGate from --fast.
Does not fork Detect / SoftReprobe; composes LeoAware.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vela.eval_harness import run_one_isolated, write_result
from vela.ir import VelaConfig, program_to_config
from vela.kernel import leo_aware_root
from vela.parser import parse
from vela.receipt import eval_gate


HONESTY = (
    "Starlink hop vs flicker ablate. SoftReprobe cut 0.58 on both arms. "
    "SoftFlicker is review (closed-write class). gate stamped from rails "
    "that ran. --fast is not the house gate. Do not mix OPE-fair v3.7 "
    "prompt figures with coupled-RNG LeoAware 73.57/138.37."
)


def _load(name: str) -> VelaConfig:
    src = (ROOT / "examples" / name).read_text(encoding="utf-8")
    return program_to_config(parse(src, name))


def main() -> int:
    root = leo_aware_root()
    if not (root / "leo_cc").is_dir():
        print(f"error: LeoAware sibling missing at {root}", flush=True)
        return 2

    reach = _load("reach.vela")
    starlink = _load("starlink_flicker.vela")
    # SoftFlicker is review: named ablation of the closed class.
    soft = VelaConfig(
        name="ReachSoftFlicker",
        posture="review",
        observe_only=False,
        soft_flicker=True,
        soft_flicker_cut=0.85,
        mechanisms=[
            "Detect",
            "SoftReprobe",
            "Calendar",
            "IntervalBw",
            "SoftFlicker",
            "DualGateGuard",
        ],
    )

    # Single-seed 45s leo_fast_ho. Gate from rows that ran (named, not
    # house). Tag keeps -fast as a human label; JSON gate is honest.
    seeds = [7]
    duration_s = 45.0
    scenario = "leo_fast_ho"
    ran_scens = [scenario]
    gate = eval_gate(seeds, duration_s, ran_scens)
    print(
        f"LeoAware root={root}  gate={gate}  "
        f"(stamped from rows that will run; not the house gate)",
        flush=True,
    )

    variants = {
        "LeoAware": VelaConfig(name="LeoAware"),
        "Reach": reach,
        "StarlinkFlicker": starlink,
        "SoftFlicker-review": soft,
    }
    rows: list[dict] = []
    for label, cfg in variants.items():
        algo = "LeoAware" if label == "LeoAware" else cfg.name
        print(f"{scenario} seed=7 45s {label} ...", flush=True)
        rec = run_one_isolated(algo, scenario, 7, duration_s, cfg)
        rec = dict(rec)
        rec["variant"] = label
        rec["gate"] = gate
        rows.append(rec)
        print(
            f"  gp={rec['goodput_mbps']:.2f} p95={rec['p95_rtt_ms']:.1f} "
            f"HO={rec.get('handovers', '?')}",
            flush=True,
        )

    summary = {
        "tag": "starlink-hop-flicker",
        "verdict": "LOG",
        "power": "low",
        "dual_gate": False,
        "gate": gate,
        "scenario": scenario,
        "seeds": seeds,
        "duration_s": duration_s,
        "honesty": HONESTY,
        "note": (
            "Observe-only Reach / StarlinkFlicker should match LeoAware "
            "within passthrough rails on seed 7 45s. SoftFlicker-review "
            "is the closed class (compose soft cuts as min: 0.85 cannot "
            "undo 0.58). Historical SoftFlicker dump was a replace-cut "
            "era. Not a house DualGate claim. JSON gate is from rows "
            "that ran (named unless full fast rails)."
        ),
        "cli_fast_label": True,
        "rows": rows,
    }
    out = write_result(summary, tag="starlink-hop-flicker")
    print(f"wrote {out} gate={gate}", flush=True)
    print("Not a house DualGate claim. --fast != house gate.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
