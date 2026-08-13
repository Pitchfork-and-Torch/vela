"""VELA mechanism IR (config the kernel runs)."""
from __future__ import annotations

from dataclasses import dataclass, field

from vela.ast import Program


@dataclass
class VelaConfig:
    name: str = "Horizon"
    mechanisms: list[str] = field(default_factory=list)
    predictive_freeze: bool = True
    interval_bw: bool = True
    horizon_chase: bool = False
    typed_loss: bool = True
    dual_gate_guard: bool = True
    oce_legacy: bool = False
    freeze_lead_rtts: float = 1.40
    chase_rtts: float = 2.60
    chase_bdp_div: float = 1.26
    rollback_delay: float = 1.40
    pre_ho_pace: float = 0.94
    seeds: list[int] = field(default_factory=lambda: [13, 7, 42, 99, 123])
    scenarios: list[str] = field(default_factory=lambda: ["leo_fast_ho", "terrestrial"])
    duration_s: float = 90.0
    baseline: str = "BBRv3approx"
    contract_name: str = "DualGate"


def program_to_config(prog: Program) -> VelaConfig:
    c = prog.controllers[0]
    mechs = list(c.compose) or [
        "Detect",
        "SoftReprobe",
        "IntervalBw",
        "PredictiveFreeze",
        "HorizonChase",
        "DualGateGuard",
    ]
    cfg = VelaConfig(name=c.name, mechanisms=mechs)
    cfg.predictive_freeze = "PredictiveFreeze" in mechs
    cfg.interval_bw = "IntervalBw" in mechs
    cfg.horizon_chase = "HorizonChase" in mechs
    cfg.typed_loss = "TypedLoss" in mechs or any(o.event == "Loss" for o in c.ons)
    cfg.dual_gate_guard = "DualGateGuard" in mechs
    cfg.oce_legacy = "OCE" in mechs and "HorizonChase" not in mechs
    if prog.contracts:
        con = prog.contracts[0]
        cfg.seeds = list(con.seeds)
        cfg.scenarios = list(con.scenarios)
        if "terrestrial" not in cfg.scenarios:
            cfg.scenarios.append("terrestrial")
        cfg.duration_s = float(con.duration_s)
        cfg.baseline = con.baseline
        cfg.contract_name = con.name
    return cfg
