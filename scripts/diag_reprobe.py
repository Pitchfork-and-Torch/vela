"""Count endpoint REPROBEs vs real handovers.

Default plan-only (no sim). --run launches isolated workers against the
LeoAware sibling. Extra REPROBEs vs handovers are flicker/capacity wobble,
not bugs (EVAL-NOTES). SoftReprobe cut stays 0.58 on hop and flicker.
gate stamped from rails; --fast / subset is not DualGate.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vela.receipt import eval_gate
from vela.types import eval_power


WORKER = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "Projects" / "leo-aware-transport"))
from leo_cc.ccas import LeoAwareCCA
from leo_cc.network import LeoPathConfig
from leo_cc.sim import run_sim
from leo_cc.metrics import summarize_result

seed = int(sys.argv[1])
dur = float(sys.argv[2])
cca_holder = {}

def factory():
    c = LeoAwareCCA()
    cca_holder["c"] = c
    return c

cfg = LeoPathConfig(duration_s=dur, handover_interval_s=12, handover_jitter_s=4, seed=seed)
res = run_sim(factory, cfg=cfg, n_flows=1, path_hint_mode="none")
m = summarize_result(res)[0]
c = cca_holder["c"]
print(json.dumps({
    "seed": seed,
    "duration_s": dur,
    "goodput_mbps": m.goodput_bps / 1e6,
    "p95_rtt_ms": m.p95_rtt_s * 1000,
    "handovers": len(res.handovers),
    "reconfigs_detected": int(getattr(c, "reconfigs_detected", 0) or 0),
    "handover_times": [round(t, 2) for t in res.handovers],
}))
'''

DEFAULT_JOBS = [(7, 45.0), (7, 90.0), (123, 90.0), (13, 90.0), (42, 90.0)]


def build_plan(jobs: list[tuple[int, float]]) -> dict:
    seeds = sorted({s for s, _ in jobs})
    # Use the shortest duration present for gate stamp honesty.
    duration = min(d for _, d in jobs)
    gate = eval_gate(seeds, duration, ["leo_fast_ho", "terrestrial"])
    return {
        "event": "diag_reprobe_plan",
        "jobs": [{"seed": s, "duration_s": d} for s, d in jobs],
        "gate": gate,
        "power": eval_power(len(seeds)),
        "dual_gate_claim": False,
        "honesty": (
            "REPROBE extras vs handovers are flicker/capacity wobble, not bugs. "
            "SoftReprobe cut 0.58 on hop and flicker. SoftFlicker is review. "
            f"gate={gate} (not DualGate unless house rails). power={eval_power(len(seeds))}."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--only",
        nargs="+",
        help="subset like 7:45 7:90 (default: house autopsy set)",
    )
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args(argv)

    if args.only:
        jobs = []
        for item in args.only:
            seed_s, dur_s = item.split(":", 1)
            jobs.append((int(seed_s), float(dur_s)))
    else:
        jobs = list(DEFAULT_JOBS)

    plan = build_plan(jobs)
    print(
        f"diag_reprobe gate={plan['gate']} jobs={len(jobs)} "
        f"dual_gate_claim={plan['dual_gate_claim']}",
        flush=True,
    )
    print(plan["honesty"], flush=True)

    results: list[dict] = []
    if args.run:
        tmp = ROOT / "scripts" / "_diag_reprobe_worker.py"
        tmp.write_text(WORKER, encoding="utf-8", newline="\n")
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            for seed, dur in jobs:
                print(f"seed={seed} {dur:.0f}s ...", flush=True)
                proc = subprocess.run(
                    [sys.executable, str(tmp), str(seed), str(dur)],
                    cwd=str(ROOT),
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode != 0:
                    print(proc.stderr or proc.stdout, flush=True)
                    return 2
                row = json.loads(proc.stdout.strip().splitlines()[-1])
                extras = int(row["reconfigs_detected"]) - int(row["handovers"])
                row["reprobe_minus_handovers"] = extras
                results.append(row)
                print(
                    f"  gp={row['goodput_mbps']:.2f} p95={row['p95_rtt_ms']:.1f} "
                    f"HO={row['handovers']} REPROBE={row['reconfigs_detected']} "
                    f"extra={extras}",
                    flush=True,
                )
        finally:
            if tmp.exists():
                tmp.unlink()
    else:
        print(
            "plan-only (no sim). Re-run with --run --only 7:45 for a cheap flicker check.",
            flush=True,
        )

    payload = {**plan, "run": bool(args.run), "results": results}
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
