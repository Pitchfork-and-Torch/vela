"""Runtime compose combinators.

Check-time already requires `compose cuts = min` for two hard epoch cuts.
Soft cuts compose as min without a clause: the more conservative remaining
fraction wins. That is the language answer to OCE stacked on SER
double-moving the window. SoftFlicker 0.85 cannot undo SoftReprobe 0.58.
"""
from __future__ import annotations

from vela.types import STDLIB_MECHANISMS


def compose_soft_cuts(factors: list[float]) -> float:
    """Min of remaining fractions in (0, 1]. Empty / all-invalid is identity 1.0.

    A cut is a remaining window fraction. Negatives, zeros, NaNs, and values
    above 1.0 are not remaining fractions: drop them so a bad factor cannot
    drive cwnd negative, to NaN, or grow the window through the cut path.
    """
    xs: list[float] = []
    for raw in factors:
        x = float(raw)
        if x != x:  # NaN
            continue
        if 0.0 < x <= 1.0:
            xs.append(x)
    if not xs:
        return 1.0
    return min(xs)


def apply_composed_cut(before_cwnd: float, factors: list[float]) -> float:
    if before_cwnd <= 0:
        return before_cwnd
    return before_cwnd * compose_soft_cuts(factors)


def soft_cut_mechanisms() -> tuple[str, ...]:
    return tuple(
        n for n, spec in STDLIB_MECHANISMS.items() if spec.get("cuts") == "soft"
    )
