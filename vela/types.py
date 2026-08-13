"""VELA type system: epochs, intervals, loss, compose effects."""
from __future__ import annotations

from dataclasses import dataclass, field


LOSS_KINDS = ("Mobility", "Congestive", "Unknown")

STDLIB_MECHANISMS = {
    "Detect": {"reads": {"rtt", "epoch"}, "writes": {"reconfig"}, "cuts": "none", "phase": "ack"},
    "SoftReprobe": {
        "reads": {"reconfig", "prior"},
        "writes": {"cwnd", "min_rtt", "bw", "epoch"},
        "cuts": "hard",
        "phase": "epoch",
    },
    "IntervalBw": {"reads": {"delivery", "epoch"}, "writes": {"bw"}, "cuts": "none", "phase": "ack"},
    "PredictiveFreeze": {
        "reads": {"p_ho", "rtt"},
        "writes": {"pace", "freeze"},
        "cuts": "none",
        "phase": "ack",
    },
    "HorizonChase": {
        "reads": {"bw", "delay_ratio", "epoch"},
        "writes": {"cwnd", "pace"},
        "cuts": "soft",
        "phase": "ack",
    },
    "DualGateGuard": {
        "reads": {"goodput", "p95"},
        "writes": {"chase_gain"},
        "cuts": "none",
        "phase": "both",
    },
    "OCE": {
        "reads": {"bw", "delay_ratio"},
        "writes": {"cwnd"},
        "cuts": "soft",
        "phase": "ack",
    },
    "TypedLoss": {
        "reads": {"loss", "delay_ratio"},
        "writes": {"cwnd"},
        "cuts": "hard",
        "phase": "ack",
    },
    "FairMode": {
        "reads": {"bdp", "delay_ratio"},
        "writes": {"cwnd"},
        "cuts": "soft",
        "phase": "ack",
    },
    "Calendar": {
        "reads": {"reconfig"},
        "writes": {"p_ho"},
        "cuts": "none",
        "phase": "epoch",
    },
    "WriteBudget": {
        "reads": {"epoch"},
        "writes": {"budget"},
        "cuts": "none",
        "phase": "epoch",
    },
    "TrimHold": {
        "reads": {"p_ho", "cwnd"},
        "writes": {"cwnd"},
        "cuts": "none",
        "phase": "ack",
    },
    "TrimFill": {
        "reads": {"prior", "cwnd", "delay_ratio"},
        "writes": {"cwnd"},
        "cuts": "soft",
        "phase": "ack",
    },
    "TrimReclaim": {
        "reads": {"epoch", "delay_ratio", "uncertainty"},
        "writes": {"cwnd"},
        "cuts": "soft",
        "phase": "ack",
    },
    "QuietReach": {
        "reads": {"bw", "epoch", "delay_ratio", "p_ho"},
        "writes": {"cwnd"},
        "cuts": "soft",
        "phase": "ack",
    },
    "QuietShield": {
        "reads": {"epoch", "delay_ratio", "p_ho"},
        "writes": {"reconfig"},
        "cuts": "none",
        "phase": "epoch",
    },
    "SoftFlicker": {
        "reads": {"reconfig", "delay_ratio"},
        "writes": {"cwnd"},
        "cuts": "soft",
        "phase": "epoch",
    },
}

FRESH_TYPES = {"Sample", "Interval", "min_rtt", "bw"}


@dataclass
class CheckResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mechanisms: list[str] = field(default_factory=list)

    def raise_if_error(self) -> None:
        if not self.ok:
            raise TypeError("VELA check failed:\n  " + "\n  ".join(self.errors))
