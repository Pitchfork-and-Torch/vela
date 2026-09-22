"""One honest Starlink efficacy surface for `vela eval` / receipt CLI.

Prints together, when present:
  eval_law, dead_seconds (hop / RttHop), flicker_dead_ms (Flicker), power

Does not compute hop/flicker dead metrics (those live on open cooks #46 / #53).
This module only formats summary / receipt dict keys into one ASCII line so
Starlink efficacy is a single readable surface once those blocks land.

SoftReprobe cut stays 0.58. Observe-only. No Detect/SoftReprobe fork.
No closed-write. No dish Mbps claim.
"""
from __future__ import annotations

from typing import Any

# House SoftReprobe cut (types.HOUSE_ENDPOINT_CUT). Named here so the CLI
# line stays honest without importing checker state.
SOFT_REPROBE_CUT = 0.58
HOP_LABEL = "hop; not Flicker"
FLICKER_LABEL = "Flicker; not RttHop"


def _fmt_num(val: Any, digits: int) -> str:
    if isinstance(val, bool) or val is None:
        return "n/a"
    if isinstance(val, (int, float)):
        return f"{float(val):.{digits}f}"
    return "n/a"


def _dead_seconds_part(block: Any) -> str | None:
    """Hop dead_seconds fragment. Understands #46 summary shape."""
    if not isinstance(block, dict):
        return None
    mean = block.get("dead_s_mean")
    # Prefer p95 when stamped; else median for forward-compat with #46.
    p95 = block.get("dead_s_p95", block.get("dead_s_median"))
    if mean is None and p95 is None and not block.get("metric"):
        return None
    return (
        f"dead_seconds mean={_fmt_num(mean, 6)} "
        f"p95={_fmt_num(p95, 6)} ({HOP_LABEL})"
    )


def _flicker_dead_part(block: Any) -> str | None:
    """Flicker dead-ms fragment. Understands #53 summary shape."""
    if not isinstance(block, dict):
        return None
    mean = block.get("flicker_dead_ms_mean")
    p95 = block.get("flicker_dead_ms_p95")
    if mean is None and p95 is None and not block.get("metric"):
        return None
    return (
        f"flicker_dead_ms mean={_fmt_num(mean, 3)} "
        f"p95={_fmt_num(p95, 3)} ({FLICKER_LABEL})"
    )


def _eval_law_part(payload: dict[str, Any]) -> str | None:
    law = payload.get("eval_law")
    if law is None or law == "":
        return None
    return f"eval_law={law}"


def _power_part(payload: dict[str, Any]) -> str | None:
    power = payload.get("power")
    if power is None or power == "":
        return None
    return f"power={power}"


def merge_efficacy_payload(
    summary: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge receipt + summary so CLI can print one line from either surface.

    Summary wins on shared keys when both carry a value (eval rows bind).
    """
    out: dict[str, Any] = {}
    for src in (receipt, summary):
        if not isinstance(src, dict):
            continue
        for key in ("eval_law", "dead_seconds", "flicker_dead_ms", "power"):
            if key in src and src.get(key) is not None and src.get(key) != "":
                out[key] = src[key]
    return out


def format_efficacy_summary_line(
    summary: dict[str, Any] | None = None,
    *,
    receipt: dict[str, Any] | None = None,
) -> str:
    """One ASCII efficacy line. Omits absent fields. Empty -> ''.

    Example (all present):
      efficacy  eval_law=coupled-rng-v3.4-p95  dead_seconds mean=1.200000
      p95=2.000000 (hop; not Flicker)  flicker_dead_ms mean=800.000
      p95=900.000 (Flicker; not RttHop)  power=low  SoftReprobe=0.58
    """
    payload = merge_efficacy_payload(summary, receipt)
    parts: list[str] = []
    law = _eval_law_part(payload)
    if law:
        parts.append(law)
    hop = _dead_seconds_part(payload.get("dead_seconds"))
    if hop:
        parts.append(hop)
    flick = _flicker_dead_part(payload.get("flicker_dead_ms"))
    if flick:
        parts.append(flick)
    power = _power_part(payload)
    if power:
        parts.append(power)
    if not parts:
        return ""
    # SoftReprobe cut named once on the surface (hop + flicker share it).
    parts.append(f"SoftReprobe={SOFT_REPROBE_CUT}")
    return "efficacy  " + "  ".join(parts)


def print_efficacy_summary(
    summary: dict[str, Any] | None = None,
    *,
    receipt: dict[str, Any] | None = None,
) -> str:
    """Print the efficacy line when non-empty. Returns the line (or '')."""
    line = format_efficacy_summary_line(summary, receipt=receipt)
    if line:
        print(line)
    return line
