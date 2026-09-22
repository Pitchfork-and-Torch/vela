"""Joined eval summary for Starlink efficacy arms.

One CLI line names eval_law, hop dead_seconds, and flicker_dead_ms
together. The metric math stays on the cooks that own those stamps.
A missing stamp prints not-stamped. This module does not invent a mean,
does not fork Detect or SoftReprobe, and does not claim dish throughput.
"""
from __future__ import annotations

from typing import Any

from vela.types import HOUSE_ENDPOINT_CUT

_NOTE = (
    "Hop dead_seconds and Flicker flicker_dead_ms are separate arms. "
    "Do not mix OPE-fair v3.7 with coupled-rng v3.4-p95. "
    "Not a dish Mbps claim."
)
_LAW_BANNED = ("mbps", "mbit", "gibps")


def efficacy_view(summary: dict | None) -> dict[str, Any]:
    """Normalize the three arms. Missing stamps stay missing."""
    src = summary if isinstance(summary, dict) else {}
    dead_b = _block(src, "dead_seconds")
    flick_b = _block(src, "flicker_dead_ms")
    dead_on = _status(dead_b) == "stamped"
    flick_on = _status(flick_b) == "stamped"
    return {
        "eval_law": _law(src),
        "dead_seconds": {
            "status": "stamped" if dead_on else "not-stamped",
            "arm": "RttHop",
            "mean": _pull(dead_b, ("dead_s_mean", "mean"), 6) if dead_on else None,
            "p95": _pull(dead_b, ("dead_s_p95", "p95"), 6) if dead_on else None,
            "median": _pull(dead_b, ("dead_s_median", "median"), 6) if dead_on else None,
        },
        "flicker_dead_ms": {
            "status": "stamped" if flick_on else "not-stamped",
            "arm": "Flicker",
            "not_arm": "RttHop",
            "mean": _pull(flick_b, ("flicker_dead_ms_mean", "mean"), 3) if flick_on else None,
            "p95": _pull(flick_b, ("flicker_dead_ms_p95", "p95"), 3) if flick_on else None,
        },
        "soft_reprobe_cut": HOUSE_ENDPOINT_CUT,
        "note": _NOTE,
    }


def attach_efficacy(summary: dict) -> dict:
    """Stamp summary['efficacy'] from the raw arms. Does not compute them."""
    if not isinstance(summary, dict):
        raise TypeError("eval summary must be a dict")
    summary["efficacy"] = efficacy_view(summary)
    return summary


def format_efficacy_cli(summary: dict | None) -> str:
    """One ASCII line: eval_law, dead_seconds, flicker_dead_ms, cut."""
    view = efficacy_view(summary)
    dead = _arm_text("dead_seconds", view["dead_seconds"], "(RttHop)", 6)
    flick = _arm_text(
        "flicker_dead_ms",
        view["flicker_dead_ms"],
        "(Flicker; not RttHop)",
        3,
    )
    cut = f"{float(view['soft_reprobe_cut']):.2f}"
    return f"efficacy  eval_law={view['eval_law']}  {dead}  {flick}  cut={cut}"


def _block(summary: dict, key: str) -> dict | None:
    raw = summary.get(key)
    if isinstance(raw, dict):
        return raw
    return None


def _status(block: dict | None) -> str:
    if not isinstance(block, dict):
        return "not-stamped"
    if block.get("status") == "not-stamped":
        return "not-stamped"
    return "stamped"


def _law(summary: dict) -> str:
    raw = summary.get("eval_law")
    if not isinstance(raw, str):
        return "not-stamped"
    text = " ".join(raw.split())
    if not text:
        return "not-stamped"
    low = text.lower()
    if any(token in low for token in _LAW_BANNED):
        return "not-stamped"
    ope = "ope-fair" in low or "ope fair" in low
    coupled = "coupled-rng" in low or "coupled rng" in low
    if ope and coupled:
        return "mixed"
    return text.replace(" ", "-")


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _pull(block: dict | None, keys: tuple[str, ...], places: int) -> float | None:
    if not isinstance(block, dict):
        return None
    for key in keys:
        if key not in block or block[key] is None:
            continue
        num = _as_float(block[key])
        if num is None:
            continue
        return round(num, places)
    return None


def _arm_text(name: str, arm: dict, label: str, places: int) -> str:
    if arm.get("status") != "stamped":
        return f"{name}=not-stamped {label}"
    bits = [name]
    mean = arm.get("mean")
    if mean is None:
        bits.append("mean=n/a")
    else:
        bits.append(f"mean={float(mean):.{places}f}")
    if arm.get("p95") is not None:
        bits.append(f"p95={float(arm['p95']):.{places}f}")
    if arm.get("median") is not None:
        bits.append(f"median={float(arm['median']):.{places}f}")
    return " ".join(bits) + f" {label}"
