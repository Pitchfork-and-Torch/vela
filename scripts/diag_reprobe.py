"""Count endpoint REPROBEs vs real handovers. Isolated.

Hop vs flicker labels (EVAL-NOTES):
  hop     = real handover count (RttHop)
  flicker = detect - HO extras (mid-epoch capacity wobble / counterfeit
            epochs). Not a hop bug. SoftReprobe cut stays 0.58 on both.
SoftFlicker / QuietShield stay review / closed-write; this diag does not
enable them. Use --dry-run to print the job plan without a sim.

Resolves LeoAware via leo_aware_root() / LEO_AWARE_TRANSPORT.
Does not fork Detect / SoftReprobe.
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

from vela.kernel import leo_aware_root
from vela.types import HOUSE_ENDPOINT_CUT


DEFAULT_JOBS = [(7, 45.0), (7, 90.0), (123, 90.0), (13, 90.0), (42, 90.0)]

WORKER = r'''
import json, sys
from pathlib import Path
leo = Path(sys.argv[3])
sys.path.insert(0, str(leo))
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
    "note": "detect-HO extras are flicker-class, not hop bugs",
    "soft_reprobe_cut": 0.58,
}))
'''


def build_plan(jobs: list[tuple[int, float]]) -> dict:
    return {
        "event": "diag_reprobe_plan",
        "jobs": [{"seed": s, "duration_s": d} for s, d in jobs],
        "soft_reprobe_cut": HOUSE_ENDPOINT_CUT,
        "hop_vs_flicker": {
            "hop": "handovers (RttHop / real HO)",
            "flicker": "detect - HO extras (capacity wobble; not a hop bug)",
        },
        "refused_on_observe": ["SoftFlicker", "QuietShield"],
        "honesty": (
            f"SoftReprobe cut {HOUSE_ENDPOINT_CUT} on hop and flicker. "
            "SoftFlicker/QuietShield not enabled by this diag. "
            "Not a house DualGate claim."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="print hop/flicker labeled job plan; no sim",
    )
    ap.add_argument("--json-out", type=Path, help="write plan JSON (dry-run friendly)")
    args = ap.parse_args(argv)

    plan = build_plan(DEFAULT_JOBS)
    print(plan["honesty"], flush=True)
    print(
        f"hop: {plan['hop_vs_flicker']['hop']}\n"
        f"flicker: {plan['hop_vs_flicker']['flicker']}",
        flush=True,
    )

    if args.dry_run:
        print(
            f"dry-run jobs={plan['jobs']} "
            f"refused_on_observe={plan['refused_on_observe']}",
            flush=True,
        )
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(
                json.dumps({**plan, "dry_run": True}, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"wrote {args.json_out}", flush=True)
        return 0

    leo = leo_aware_root()
    if not (leo / "leo_cc").is_dir():
        print(f"error: LeoAware sibling missing at {leo}", flush=True)
        return 2
    tmp = ROOT / "scripts" / "_diag_reprobe_worker.py"
    tmp.write_text(WORKER, encoding="utf-8", newline="\n")
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    print(f"LeoAware root={leo}", flush=True)
    try:
        for seed, dur in DEFAULT_JOBS:
            print(f"seed={seed} {dur:.0f}s ...", flush=True)
            proc = subprocess.run(
                [sys.executable, str(tmp), str(seed), str(dur), str(leo)],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if proc.returncode != 0:
                print(proc.stderr[-400:], flush=True)
                continue
            rec = json.loads(proc.stdout.strip().splitlines()[-1])
            extra = rec["reconfigs_detected"] - rec["handovers"]
            print(
                f"  gp={rec['goodput_mbps']:.2f} p95={rec['p95_rtt_ms']:.1f} "
                f"hop_HO={rec['handovers']} detect={rec['reconfigs_detected']} "
                f"flicker~={extra}",
                flush=True,
            )
    finally:
        if tmp.exists():
            tmp.unlink()
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps({**plan, "dry_run": False}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
