"""No-oracle law: the endpoint cannot see the next hop.

The sibling sim (LeoAware v3.1 freeze-lead) can peek `next_capacity`
from PathState. VELA refuses that gift. PredictiveFreeze may estimate
`p_ho` from *past* inter-hop gaps. Fail-closed Hint Some may name the
current epoch. Future PathState is a type error and a kernel drop.
"""
from __future__ import annotations

# Names a program may not read. Attr or bare.
ORACLE_NAMES = frozenset(
    {
        "next_capacity",
        "next_capacity_bps",
        "next_rtt",
        "next_rtt_s",
        "next_handover",
        "next_handover_t",
        "future_capacity",
        "future_capacity_bps",
        "next_path_state",
    }
)

# Keyword args LeoAware.on_path_hint may see. next_capacity is not among them.
HINT_PASSTHROUGH = frozenset(
    {
        "capacity_bps",
        "rtt_s",
        "epoch",
        "freeze_remaining_s",
        "freeze_active",
    }
)


def refuse_oracle_hint(kw: dict) -> dict:
    """Drop future PathState. Caller must pass next_capacity_bps=None."""
    return {k: v for k, v in kw.items() if k in HINT_PASSTHROUGH}


def oracle_name_of(expr) -> str | None:
    """Return the oracle identifier if this expr names future PathState."""
    if expr is None or not hasattr(expr, "kind"):
        return None
    if expr.kind == "name" and expr.name in ORACLE_NAMES:
        return expr.name
    if expr.kind == "attr" and expr.name in ORACLE_NAMES:
        return expr.name
    if expr.kind == "attr" and expr.left is not None and expr.left.kind == "name":
        combo = f"{expr.left.name}.{expr.name}"
        if expr.name in ORACLE_NAMES or combo in {
            "path.next_capacity",
            "path.next_capacity_bps",
            "hint.next_capacity",
        }:
            return combo if expr.name not in ORACLE_NAMES else expr.name
    return None


def oracle_error(cname: str, name: str) -> str:
    return (
        f"{cname}: {name} is future PathState "
        "(no-oracle law; endpoint cannot see the next hop)"
    )
