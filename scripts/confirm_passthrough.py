"""Confirm observe-only Reach matches LeoAware on seed 7 45s.

Default is plan-only (no sim). Add --run when leo-aware-transport is
present. gate=fast for these rails; not a house DualGate claim.
Mission: observe-only wrap must match LeoAware on the same seed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vela.eval_harness import run_one_isolated
from vela.ir import VelaConfig, program_to_config
from vela.parser import parse
from vela.receipt import eval_gate
from vela.types import eval_power


def build_plan(seed: int, duration_s: float) -> dict:
    seeds = [seed]
    gate = eval_gate(seeds, duration_s, ["leo_fast_ho", "terrestrial"])
    power = eval_power(len(seeds))
    return {
        "event": "confirm_passthrough_plan",
        "seed": seed,
        "duration_s": duration_s,
        "scenario": "leo_fast_ho",
        "gate": gate,
        "power": power,
        "dual_gate_claim": False,  # fast rails never a house DualGate win
        "honesty": (
            "Observe-only Reach must match LeoAware on the same seed. "
            f"gate={gate} (not the house gate). "
            f"power={power}. dual_gate_claim=false. "
            "Do not claim DualGate from --fast / seed-7 45s."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--duration", type=float, default=45.0)
    ap.add_argument("--run", action="store_true", help="hit sibling sim")
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args(argv)

    plan = build_plan(args.seed, args.duration)
    print(
        f"confirm_passthrough gate={plan['gate']} "
        f"dual_gate_claim={plan['dual_gate_claim']} "
        f"seed={plan['seed']} duration={plan['duration_s']:g}s",
        flush=True,
    )
    print(plan["honesty"], flush=True)

    results: dict = {}
    if args.run:
        try:
            src = (ROOT / "examples" / "reach.vela").read_text(encoding="utf-8")
            cfg = program_to_config(parse(src, "reach.vela"))
            rows = {}
            for name, c, algo in (
                ("LeoAware", VelaConfig(name="LeoAware"), "LeoAware"),
                ("Reach", cfg, "Reach"),
            ):
                rec = run_one_isolated(
                    algo, plan["scenario"], plan["seed"], plan["duration_s"], c
                )
                rows[name] = {
                    "goodput_mbps": rec["goodput_mbps"],
                    "p95_rtt_ms": rec["p95_rtt_ms"],
                }
                print(
                    f"{name} {rec['goodput_mbps']:.2f}/{rec['p95_rtt_ms']:.1f}",
                    flush=True,
                )
            ok = (
                abs(rows["LeoAware"]["goodput_mbps"] - rows["Reach"]["goodput_mbps"])
                < 1e-6
                and abs(rows["LeoAware"]["p95_rtt_ms"] - rows["Reach"]["p95_rtt_ms"])
                < 1e-6
            )
            results = {"rows": rows, "match": ok}
            if not ok:
                print("MISS: Reach did not match LeoAware", flush=True)
                payload = {**plan, "run": True, "results": results}
                if args.json_out:
                    args.json_out.parent.mkdir(parents=True, exist_ok=True)
                    args.json_out.write_text(
                        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                    )
                return 3
        except Exception as exc:  # noqa: BLE001
            print(f"error: sibling sim unavailable: {exc}", flush=True)
            return 2
    else:
        print(
            "plan-only (no sim). Re-run with --run when leo-aware-transport is present.",
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
