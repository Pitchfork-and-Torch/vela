"""One-sim worker. Isolated so a CPython crash cannot kill the suite."""
from __future__ import annotations

import argparse
import json
import sys

from vela.ir import VelaConfig
from vela.kernel import make_cca, oce_cca_factory


def _factory(algo: str, cfg: VelaConfig):
    from vela.eval_harness import _import_sim

    mod = _import_sim()
    if algo == "BBRv3approx":
        return lambda: mod["BbrCCA"]()
    if algo == "LeoAware":
        return lambda: mod["LeoAwareCCA"]()
    if algo == "CUBIC":
        return lambda: mod["CubicCCA"]()
    if algo == "LeoAwareOCE":
        return oce_cca_factory()
    return make_cca(cfg)


def run_job(
    *,
    algo: str,
    scenario: str,
    seed: int,
    duration_s: float,
    cfg: VelaConfig,
) -> dict:
    from vela.eval_harness import _import_sim, run_one, scenario_cfg

    mod = _import_sim()
    scfg, n_flows = scenario_cfg(mod, scenario, seed, duration_s)
    rec = run_one(mod, _factory(algo, cfg), scfg, n_flows)
    rec.scenario = scenario
    rec.seed = seed
    rec.cca = algo
    return {
        "scenario": rec.scenario,
        "seed": rec.seed,
        "cca": rec.cca,
        "goodput_mbps": rec.goodput_mbps,
        "p95_rtt_ms": rec.p95_rtt_ms,
        "avg_rtt_ms": rec.avg_rtt_ms,
        "loss_rate": rec.loss_rate,
        "handovers": rec.handovers,
        "jain_fairness": rec.jain_fairness,
        "n_flows": rec.n_flows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--config-json", default="")
    args = ap.parse_args(argv)
    cfg = VelaConfig()
    if args.config_json:
        raw = json.loads(args.config_json)
        cfg = VelaConfig(**{k: raw[k] for k in VelaConfig.__dataclass_fields__ if k in raw})
    row = run_job(
        algo=args.algo,
        scenario=args.scenario,
        seed=args.seed,
        duration_s=args.duration,
        cfg=cfg,
    )
    sys.stdout.write(json.dumps(row))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
