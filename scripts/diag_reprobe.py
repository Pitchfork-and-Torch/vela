"""Count endpoint REPROBEs vs real handovers. Isolated."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def main() -> None:
    jobs = [(7, 45.0), (7, 90.0), (123, 90.0), (13, 90.0), (42, 90.0)]
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
                timeout=180,
            )
            if proc.returncode != 0:
                print(proc.stderr[-400:], flush=True)
                continue
            rec = json.loads(proc.stdout.strip().splitlines()[-1])
            extra = rec["reconfigs_detected"] - rec["handovers"]
            print(
                f"  gp={rec['goodput_mbps']:.2f} p95={rec['p95_rtt_ms']:.1f} "
                f"HO={rec['handovers']} detect={rec['reconfigs_detected']} "
                f"false~={extra}",
                flush=True,
            )
    finally:
        if tmp.exists():
            tmp.unlink()


if __name__ == "__main__":
    main()
