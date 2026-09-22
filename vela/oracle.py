"""No-oracle law: the endpoint cannot see the next hop.

The sibling sim (LeoAware v3.1 freeze-lead) can peek `next_capacity`
from PathState. VELA refuses that gift. PredictiveFreeze may estimate
`p_ho` from *past* inter-hop gaps. Fail-closed Hint Some may name the
current epoch. Future PathState is a type error and a kernel drop.

Hint role + age (LANGUAGE.md): ASCENT-D integrity stops bit flips. It
does not stop a malicious or stale honest hint with a valid MAC. Role
mismatch and stale age fail closed at check/runtime. They are not a PKI.
"""
from __future__ import annotations

from vela.types import HINT_TRUSTED_ROLES, HOUSE_HINT_MAX_AGE_S

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


def hint_role_ok(role: str | None) -> bool:
    """True when ROLE is in the trusted ASCENT set (pilot | gateway)."""
    if role is None:
        return False
    return str(role).strip().lower() in HINT_TRUSTED_ROLES


def hint_age_ok(age_s: float | None, max_age_s: float | None = None) -> bool:
    """True when age is present and strictly below the house (or given) bound."""
    if age_s is None:
        return False
    try:
        age = float(age_s)
    except (TypeError, ValueError):
        return False
    if age < 0.0:
        return False
    bound = HOUSE_HINT_MAX_AGE_S if max_age_s is None else float(max_age_s)
    if bound <= 0.0:
        return False
    return age < bound


def hint_role_age_accept(
    role: str | None,
    age_s: float | None,
    *,
    max_age_s: float | None = None,
) -> bool:
    """Fail-closed Option gate: role mismatch or stale age => treat as None."""
    return hint_role_ok(role) and hint_age_ok(age_s, max_age_s=max_age_s)
