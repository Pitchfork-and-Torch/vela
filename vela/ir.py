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
    trim_hold: bool = False
    trim_fill: bool = False
    trim_reclaim: bool = False
    trim_hold_p_ho: float = 0.72
    trim_fill_frac: float = 0.65
    trim_fill_steps: int = 6
    trim_fill_window_s: float = 0.10
    trim_reclaim_budget_mss: float = 12.0
    quiet_shield: bool = False
    quiet_shield_age_s: float = 7.5
    quiet_shield_dr: float = 1.40
    quiet_shield_min_gaps: int = 2
    soft_flicker: bool = False
    soft_flicker_cut: float = 0.85
    soft_flicker_dr: float = 1.20
    quiet_reach: bool = False
    quiet_reach_age_s: float = 2.2
    quiet_reach_clean_s: float = 0.28
    quiet_reach_p_ho: float = 0.22
    quiet_reach_dr: float = 1.16
    quiet_reach_frac: float = 1.28
    quiet_reach_shots: int = 3
    quiet_reach_shot_gap_s: float = 1.0
    quiet_reach_max_mult: float = 1.22
    quiet_reach_max_mss: float = 18.0
    quiet_reach_max_uncert: float = 0.90
    slack_p90_s: float = 0.130
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
    cfg.trim_hold = "TrimHold" in mechs
    cfg.trim_fill = "TrimFill" in mechs
    cfg.trim_reclaim = "TrimReclaim" in mechs
    cfg.quiet_reach = "QuietReach" in mechs
    cfg.quiet_shield = "QuietShield" in mechs
    cfg.soft_flicker = "SoftFlicker" in mechs
    if cfg.trim_hold or cfg.trim_fill or cfg.trim_reclaim or cfg.quiet_reach:
        cfg.interval_bw = True
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
