"""Dual-gate eval: VELA controller vs LeoAware and BBR on leo-aware-transport."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Callable

from vela.ir import VelaConfig, parse_report_ci
from vela.kernel import make_cca, oce_cca_factory
from vela.types import POWER_OK_MIN_SEEDS, eval_power

# Seed 7 45s locked LeoAware rails (WORKDAY / EVAL-NOTES). Not house-gate.
LEO_S7_45_GP = 88.65
LEO_S7_45_P95 = 108.4
PASSTHROUGH_GP_ABS = 0.05
PASSTHROUGH_P95_ABS = 0.2
PASSTHROUGH_LEO_GP_ABS = 0.15


def passthrough_ok(leo: dict, reach: dict) -> bool:
    """Observe-only Reach vs LeoAware on one seed. Not a dual-gate."""
    return (
        abs(float(reach["goodput_mbps"]) - float(leo["goodput_mbps"])) <= PASSTHROUGH_GP_ABS
        and abs(float(reach["p95_rtt_ms"]) - float(leo["p95_rtt_ms"])) <= PASSTHROUGH_P95_ABS
        and abs(float(leo["goodput_mbps"]) - LEO_S7_45_GP) <= PASSTHROUGH_LEO_GP_ABS
    )


def write_passthrough_result(
    leo: dict,
    reach: dict,
    *,
    ok: bool,
    ran: str,
) -> Path:
    """Local claim file. results/*.json is gitignored on purpose."""
    summary = {
        "tag": "reach-passthrough",
        "ran": ran,
        "verdict": "MATCH" if ok else "MISS",
        "power": "low",
        "dual_gate": False,
        "ok": bool(ok),
        "note": (
            "Observe-only Reach vs LeoAware on seed 7 45s. "
            "Not a house-gate dual-gate claim."
        ),
        "honesty": (
            "Means only. Do not mix with OPE-fair v3.7 prompt figures. "
            "House champion remains LeoAware v3.4-p95 73.57/138.37 vs BBR 70.88/138.83."
        ),
        "scenario": "leo_fast_ho",
        "seed": 7,
        "duration_s": 45.0,
        "rails": {
            "gp_abs_mbps": PASSTHROUGH_GP_ABS,
            "p95_abs_ms": PASSTHROUGH_P95_ABS,
            "leo_locked_gp": LEO_S7_45_GP,
            "leo_locked_p95": LEO_S7_45_P95,
        },
        "leo": leo,
        "reach": reach,
    }
    return write_result(summary, tag="reach-passthrough")


def _leo_root() -> Path:
    return Path.home() / "Projects" / "leo-aware-transport"


def _import_sim():
    root = _leo_root()
    if not root.is_dir():
        raise FileNotFoundError(f"leo-aware-transport not found at {root}")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from leo_cc.ccas import BbrCCA, CubicCCA, LeoAwareCCA
    from leo_cc.metrics import summarize_result
    from leo_cc.network import LeoPathConfig
    from leo_cc.sim import run_sim

    return {
        "BbrCCA": BbrCCA,
        "CubicCCA": CubicCCA,
        "LeoAwareCCA": LeoAwareCCA,
        "summarize_result": summarize_result,
        "LeoPathConfig": LeoPathConfig,
        "run_sim": run_sim,
    }


def scenario_cfg(mod, name: str, seed: int, duration_s: float):
    LeoPathConfig = mod["LeoPathConfig"]
    if name == "leo_fast_ho":
        return (
            LeoPathConfig(
                duration_s=duration_s,
                handover_interval_s=12,
                handover_jitter_s=4,
                seed=seed,
            ),
            1,
        )
    if name == "leo_single":
        return (LeoPathConfig(duration_s=duration_s, handover_interval_s=22, seed=seed), 1)
    if name == "terrestrial":
        d = min(duration_s, 60.0)
        return (LeoPathConfig(duration_s=d, seed=seed, terrestrial=True), 1)
    raise ValueError(name)


@dataclass
class Row:
    scenario: str
    seed: int
    cca: str
    goodput_mbps: float
    p95_rtt_ms: float
    avg_rtt_ms: float
    loss_rate: float
    handovers: int


def run_one(mod, factory: Callable, cfg, n_flows: int) -> Row:
    run_sim = mod["run_sim"]
    summarize_result = mod["summarize_result"]
    res = run_sim(factory, cfg=cfg, n_flows=n_flows, path_hint_mode="none")
    metrics = summarize_result(res)
    m = metrics[0]
    name = getattr(factory(), "name", "cca")
    try:
        name = factory().name
    except Exception:
        name = m.name
    return Row(
        scenario="",
        seed=0,
        cca=name,
        goodput_mbps=m.goodput_bps / 1e6,
        p95_rtt_ms=m.p95_rtt_s * 1000,
        avg_rtt_ms=m.avg_rtt_s * 1000,
        loss_rate=m.loss_rate,
        handovers=len(res.handovers),
    )


def _cfg_json(cfg: VelaConfig) -> str:
    return json.dumps({f.name: getattr(cfg, f.name) for f in fields(cfg)})


def run_one_isolated(
    algo: str,
    scenario: str,
    seed: int,
    duration_s: float,
    cfg: VelaConfig,
    *,
    retries: int = 1,
) -> dict:
    """Run one sim in a child process. Retry once on interpreter crash."""
    root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        "-m",
        "vela.eval_worker",
        "--algo",
        algo,
        "--scenario",
        scenario,
        "--seed",
        str(seed),
        "--duration",
        str(duration_s),
        "--config-json",
        _cfg_json(cfg),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    last_err = ""
    for attempt in range(retries + 1):
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                timeout=max(120.0, duration_s * 8.0),
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            last_err = f"timeout: {e}"
            print(f"  retry after timeout ({attempt + 1})", flush=True)
            continue
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout.strip().splitlines()[-1])
        last_err = (proc.stderr or proc.stdout or f"exit {proc.returncode}")[-500:]
        print(f"  worker fail attempt {attempt + 1}: {last_err[:180]}", flush=True)
    raise RuntimeError(f"isolated sim failed {algo} {scenario} seed={seed}: {last_err}")


def evaluate(
    cfg: VelaConfig,
    *,
    seeds: list[int] | None = None,
    scenarios: list[str] | None = None,
    duration_s: float | None = None,
    include_oce: bool = False,
    include_cubic: bool = False,
    isolated: bool = True,
) -> dict:
    seeds = list(seeds or cfg.seeds)
    scenarios = list(scenarios or cfg.scenarios)
    duration_s = float(duration_s or cfg.duration_s)
    algo_names = ["BBRv3approx", "LeoAware", cfg.name]
    if include_oce:
        algo_names.append("LeoAwareOCE")
    if include_cubic:
        algo_names.append("CUBIC")

    rows: list[dict] = []
    t0 = time.time()
    mod = None
    for scen in scenarios:
        for seed in seeds:
            for algo_name in algo_names:
                print(f"{scen} seed={seed} {algo_name} ...", flush=True)
                if isolated:
                    rec = run_one_isolated(
                        algo_name, scen, seed, duration_s, cfg
                    )
                else:
                    if mod is None:
                        mod = _import_sim()
                    factories = {
                        "BBRv3approx": lambda: mod["BbrCCA"](),
                        "LeoAware": lambda: mod["LeoAwareCCA"](),
                        "CUBIC": lambda: mod["CubicCCA"](),
                        "LeoAwareOCE": oce_cca_factory(),
                        cfg.name: make_cca(cfg),
                    }
                    scfg, n_flows = scenario_cfg(mod, scen, seed, duration_s)
                    one = run_one(mod, factories[algo_name], scfg, n_flows)
                    one.scenario = scen
                    one.seed = seed
                    one.cca = algo_name
                    rec = asdict(one)
                rows.append(rec)
                print(
                    f"  gp={rec['goodput_mbps']:.2f} p95={rec['p95_rtt_ms']:.1f}",
                    flush=True,
                )

    summary = _summarize(rows, cfg)
    summary["elapsed_s"] = round(time.time() - t0, 2)
    summary["rows"] = rows
    summary["config"] = {
        "name": cfg.name,
        "mechanisms": cfg.mechanisms,
        "posture": cfg.posture,
        "observe_only": cfg.observe_only,
        "passthrough": cfg.passthrough,
        "seeds": seeds,
        "scenarios": scenarios,
        "duration_s": duration_s,
        "baseline": cfg.baseline,
    }
    return summary


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return var ** 0.5


def _mean_pm_std(mean: float, std: float) -> str:
    """Honest CI stand-in: mean+/-std. Not a bootstrap interval."""
    return f"{mean:.3f}+/-{std:.3f}"


def _ci_level(reports: list[str]) -> float | None:
    """Parse report ci / ci(0.95). Missing clause means no top-level ci object."""
    for item in reports:
        raw = str(item).strip()
        if raw == "ci":
            return 0.95
        if raw.startswith("ci(") and raw.endswith(")"):
            inner = raw[3:-1].strip()
            try:
                return float(inner)
            except ValueError:
                return 0.95
    return None


def _fmt_mean_std(mean: float, std: float) -> str:
    return f"{mean:.3f} +/- {std:.3f}"


def _ci_block(tables: list[dict], level: float) -> dict:
    """Honest CI object: mean +/- sample std. Not a bootstrap interval."""
    return {
        "level": level,
        "method": "mean+/-std",
        "note": (
            "Sample mean +/- sample std (ddof=1). "
            "Not a bootstrap or t-interval. Coverage is not claimed."
        ),
        "rows": [
            {
                "scenario": t["scenario"],
                "cca": t["cca"],
                "n": t["n"],
                "goodput": _fmt_mean_std(t["goodput_mean"], t["goodput_std"]),
                "p95": _fmt_mean_std(t["p95_mean"], t["p95_std"]),
                "goodput_mean": t["goodput_mean"],
                "goodput_std": t["goodput_std"],
                "p95_mean": t["p95_mean"],
                "p95_std": t["p95_std"],
            }
            for t in tables
        ],
    }


REQUIRED_ASSERTS = ("dual_gate_vs_BBR", "pareto_vs_LeoAware", "terrestrial_floor")


def _decide_verdict(asserts: list[dict], n_seeds: int, contract_min: int) -> str:
    """ACCEPT / FAIL / INCOMPLETE. Missing data is not a measured miss."""
    names = {a.get("assert") for a in asserts}
    incomplete = (
        any(a.get("note") == "INCOMPLETE" for a in asserts)
        or "terrestrial_floor" not in names
        or n_seeds < contract_min
        or any(name not in names for name in REQUIRED_ASSERTS)
    )
    if incomplete:
        return "INCOMPLETE"
    if any(not a.get("ok") for a in asserts):
        return "FAIL"
    return "ACCEPT"


def _summarize(rows: list[dict], cfg: VelaConfig) -> dict:
    by: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        by.setdefault((r["scenario"], r["cca"]), []).append(r)

    tables: list[dict] = []
    for (scen, cca), rs in sorted(by.items()):
        gps = [r["goodput_mbps"] for r in rs]
        p95s = [r["p95_rtt_ms"] for r in rs]
        gp_mean = round(_mean(gps), 3)
        gp_std = round(_std(gps), 3)
        p95_mean = round(_mean(p95s), 3)
        p95_std = round(_std(p95s), 3)
        tables.append(
            {
                "scenario": scen,
                "cca": cca,
                "n": len(rs),
                "goodput_mean": gp_mean,
                "goodput_std": gp_std,
                "goodput_ci": _mean_pm_std(gp_mean, gp_std),
                "p95_mean": p95_mean,
                "p95_std": p95_std,
                "p95_ci": _mean_pm_std(p95_mean, p95_std),
            }
        )

    def cell(scen: str, cca: str) -> dict | None:
        for t in tables:
            if t["scenario"] == scen and t["cca"] == cca:
                return t
        return None

    verdicts: list[dict] = []
    primary = "leo_fast_ho"
    cand = cell(primary, cfg.name)
    bbr = cell(primary, "BBRv3approx")
    leo = cell(primary, "LeoAware")
    if cand and bbr:
        gp_ok = cand["goodput_mean"] >= bbr["goodput_mean"]
        p95_ok = cand["p95_mean"] <= bbr["p95_mean"]
        verdicts.append(
            {
                "assert": "dual_gate_vs_BBR",
                "ok": bool(gp_ok and p95_ok),
                "goodput_mean": cand["goodput_mean"],
                "p95_mean": cand["p95_mean"],
                "bbr_goodput": bbr["goodput_mean"],
                "bbr_p95": bbr["p95_mean"],
            }
        )
    else:
        verdicts.append({"assert": "dual_gate_vs_BBR", "ok": False, "note": "INCOMPLETE"})
    if cand and leo:
        gp_delta = cand["goodput_mean"] - leo["goodput_mean"]
        p95_delta = cand["p95_mean"] - leo["p95_mean"]
        # 0.05 Mbps / 0.2 ms is sim tie noise (fast4: -0.014 Mbps / 0.0 ms)
        vs_leo_ok = gp_delta >= -0.05 and p95_delta <= 0.2
        verdicts.append(
            {
                "assert": "pareto_vs_LeoAware",
                "ok": bool(vs_leo_ok),
                "goodput_delta_mbps": round(gp_delta, 3),
                "p95_delta_ms": round(p95_delta, 3),
                "goodput_rel": round(gp_delta / leo["goodput_mean"], 4)
                if leo["goodput_mean"]
                else None,
            }
        )
    else:
        verdicts.append({"assert": "pareto_vs_LeoAware", "ok": False, "note": "INCOMPLETE"})
    terr_h = cell("terrestrial", cfg.name)
    if terr_h:
        terr_ok = terr_h["goodput_mean"] >= 77.0 and terr_h["p95_mean"] <= 40.5
        verdicts.append(
            {
                "assert": "terrestrial_floor",
                "ok": bool(terr_ok),
                "goodput_mean": terr_h["goodput_mean"],
                "p95_mean": terr_h["p95_mean"],
            }
        )
    else:
        verdicts.append({"assert": "terrestrial_floor", "ok": False, "note": "INCOMPLETE"})

    n_seeds = cand["n"] if cand else 0
    contract_min = len(cfg.seeds)
    if n_seeds < contract_min:
        verdicts.append(
            {
                "assert": "seed_count",
                "ok": False,
                "note": "INCOMPLETE",
                "n": n_seeds,
                "contract_min": contract_min,
            }
        )
    out = {
        "verdict": _decide_verdict(verdicts, n_seeds, contract_min),
        "power": eval_power(n_seeds),
        "tables": tables,
        "asserts": verdicts,
        "honesty": (
            "Means only. p-values are not claimed. "
            f"power=low when n<{POWER_OK_MIN_SEEDS}. "
            "Do not mix these numbers with OPE-fair v3.7 prompt figures."
        ),
    }
    ci_level, _ci_errs = parse_report_ci(list(getattr(cfg, "reports", []) or []))
    if ci_level is not None:
        out["ci"] = _ci_block(tables, ci_level)
    return out


def write_result(summary: dict, tag: str = "horizon") -> Path:
    out_dir = Path(__file__).resolve().parents[1] / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"eval_{tag}.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8", newline="\n")
    return path
