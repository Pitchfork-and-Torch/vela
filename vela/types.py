"""VELA type system: epochs, intervals, loss, compose effects."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


LOSS_KINDS = ("Mobility", "Congestive", "Unknown")
RECONFIG_KINDS = ("RttHop", "Flicker")
# Load-bearing SoftReprobe cut on hop and flicker. SoftFlicker 0.85 is review.
HOUSE_ENDPOINT_CUT = 0.58
# LeoAware Unknown fall-through. A cut without this delay proof is congestive guesswork.
UNKNOWN_DELAY_RATIO = 1.35
# Shared eval-power floor. House DualGate is 5 seeds: ACCEPT on means stays
# legal, but n < 8 is power=low (no p-value). Checker and harness share this.
POWER_OK_MIN_SEEDS = 8
# RFC 5166 Jain holdout. Optional contract scenario, not a silent README.
FAIRNESS_SCENARIO = "leo_multi"
KNOWN_SCENARIOS = frozenset({"leo_fast_ho", "leo_single", "terrestrial", "leo_multi"})


def eval_power(n_seeds: int) -> str:
    """Honesty label: 'low' when n < POWER_OK_MIN_SEEDS, else 'ok'."""
    return "low" if int(n_seeds) < POWER_OK_MIN_SEEDS else "ok"


def assert_names_jain(left: str) -> bool:
    s = str(left).lower().replace(" ", "")
    return "jain" in s or "fairness" in s


def parse_jain_floor(right: str) -> float | None:
    raw = str(right).strip()
    if raw.endswith("%"):
        try:
            return float(raw[:-1]) / 100.0
        except ValueError:
            return None
    try:
        val = float(raw)
    except ValueError:
        return None
    if val > 1.0 and val <= 100.0:
        val = val / 100.0
    if 0.0 < val <= 1.0:
        return val
    return None


HINT_ARMS = ("Some", "None")
HINT_TYPE_NAMES = frozenset({"Hint", "Option"})
HINT_CHANNELS = frozenset({"ascent", "orb", "orbital"})
STDLIB_MODULES = frozenset(
    {
        "std.epoch",
        "std.loss",
        "std.measure",
        "std.control",
        "std.path",
        "std.hint",
        "std.eval",
        "std.mech",
    }
)
WRITE_TARGETS = ("cwnd", "pace")
INTEGRATOR_OPS = ("*=", "+=", "-=", "/=")
POSTURES = ("observe", "review")

# LANGUAGE.md D2 closed-write class. Stdlib only until a named ablation is green.
CLOSED_WRITE_OPERATORS = frozenset(
    {
        "HorizonChase",
        "TrimFill",
        "TrimReclaim",
        "QuietReach",
        "QuietShield",
        "SoftFlicker",
        "TrimHold",
    }
)

# Closed-write class plus legacy OCE. Any of these writes the control loop.
REVIEW_WRITE_OPERATORS = CLOSED_WRITE_OPERATORS | frozenset({"OCE"})


def review_writes_in(names: Iterable[str]) -> list[str]:
    return [n for n in names if n in REVIEW_WRITE_OPERATORS]


def is_observe_only(names: Iterable[str]) -> bool:
    return not review_writes_in(names)


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
    compose_digest: str = ""
    authority: dict = field(default_factory=dict)
    views: list[str] = field(default_factory=list)
    posture: str = "observe"
    observe_only: bool = False
    closed_writes: list[str] = field(default_factory=list)
    hint_fail_closed: bool = False
    typed_reconfig: bool = False
    typed_loss: bool = False
    passthrough: bool = False
    power: str = ""
    no_oracle: bool = True
    fairness: str = ""
    jain_min: float | None = None
    cuts_compose: str = ""

    def raise_if_error(self) -> None:
        if not self.ok:
            raise TypeError("VELA check failed:\n  " + "\n  ".join(self.errors))
