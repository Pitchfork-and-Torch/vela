"""Dead seconds after handover: Starlink efficacy metric (observe-only).

MISSION: fewer dead seconds after a hop. A dead-second window is the time
after a detected RttHop (sim handover) until goodput recovers to
DEAD_SEC_RECOVER_FRAC of the pre-hop epoch median goodput.

SoftReprobe cut stays 0.58. This module measures; it does not fork Detect
or SoftReprobe and does not claim dish Mbps.
"""
from __future__ import annotations

from typing import Any, Sequence

# Recover to this fraction of the pre-hop epoch median goodput.
# Documented threshold for the first-class dead-seconds metric.
DEAD_SEC_RECOVER_FRAC = 0.80
DEAD_SEC_METRIC = "dead_seconds_after_handover"


def _median(xs: list[float]) -> float:
    if not xs:
        return float("nan")
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    if n % 2:
        return float(ys[mid])
    return 0.5 * (float(ys[mid - 1]) + float(ys[mid]))


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def compute_dead_seconds(
    t: Sequence[float],
    goodput_bps: Sequence[float],
    hop_times: Sequence[float],
    *,
    recover_frac: float = DEAD_SEC_RECOVER_FRAC,
    end_t: float | None = None,
) -> dict[str, Any]:
    """Measure dead seconds after each detected RttHop / handover.

    Pre-hop epoch for hop H at time h_i is [h_{i-1}, h_i) (or [t0, h_i)
    for the first hop). The pre-hop median is the median of goodput samples
    in that window. Dead seconds are seconds from h_i until goodput first
    reaches recover_frac * that median. If recovery never happens before
    the next hop (or end_t), the hop is censored and dead_s is the
    available post-hop window length.
    """
    definition = (
        f"seconds after detected RttHop until goodput recovers to "
        f"{recover_frac:.0%} of pre-hop epoch median goodput"
    )
    out: dict[str, Any] = {
        "metric": DEAD_SEC_METRIC,
        "recover_frac": float(recover_frac),
        "recover_pct": int(round(float(recover_frac) * 100)),
        "definition": definition,
        "hops": [],
        "n_hops": 0,
        "n_recovered": 0,
        "n_censored": 0,
        "dead_s_mean": None,
        "dead_s_median": None,
        "dead_s_total": None,
    }
    if not t or not goodput_bps or len(t) != len(goodput_bps):
        out["note"] = "empty or misaligned timeseries"
        return out
    times = [float(x) for x in t]
    gps = [float(x) for x in goodput_bps]
    hops = sorted(float(h) for h in hop_times)
    if not hops:
        out["note"] = "no detected RttHop / handover times"
        return out
    t0 = times[0]
    t_end = float(end_t) if end_t is not None else times[-1]
    hop_rows: list[dict[str, Any]] = []
    dead_vals: list[float] = []
    for i, hop_t in enumerate(hops):
        prev = hops[i - 1] if i > 0 else t0
        nxt = hops[i + 1] if i + 1 < len(hops) else t_end
        pre = [gp for tt, gp in zip(times, gps) if prev <= tt < hop_t]
        if not pre:
            # No pre-hop samples: cannot form an epoch median.
            hop_rows.append(
                {
                    "hop_t": hop_t,
                    "pre_hop_median_bps": None,
                    "threshold_bps": None,
                    "recover_t": None,
                    "dead_s": None,
                    "censored": True,
                    "note": "no pre-hop samples",
                }
            )
            continue
        med = _median(pre)
        thr = float(recover_frac) * med
        recover_t = None
        for tt, gp in zip(times, gps):
            if tt < hop_t:
                continue
            if tt > nxt:
                break
            if gp >= thr:
                recover_t = tt
                break
        if recover_t is None:
            dead_s = max(0.0, float(nxt) - hop_t)
            censored = True
        else:
            dead_s = max(0.0, float(recover_t) - hop_t)
            censored = False
        hop_rows.append(
            {
                "hop_t": hop_t,
                "pre_hop_median_bps": med,
                "threshold_bps": thr,
                "recover_t": recover_t,
                "dead_s": round(dead_s, 6),
                "censored": censored,
            }
        )
        dead_vals.append(dead_s)
    out["hops"] = hop_rows
    out["n_hops"] = len(hop_rows)
    out["n_recovered"] = sum(1 for h in hop_rows if not h.get("censored"))
    out["n_censored"] = sum(1 for h in hop_rows if h.get("censored"))
    if dead_vals:
        out["dead_s_mean"] = round(_mean(dead_vals), 6)
        out["dead_s_median"] = round(_median(dead_vals), 6)
        out["dead_s_total"] = round(sum(dead_vals), 6)
    return out


def dead_seconds_from_sim(res: Any, *, recover_frac: float = DEAD_SEC_RECOVER_FRAC) -> dict[str, Any]:
    """Compute dead-seconds from a leo-aware-transport SimResult (flow 0)."""
    hops = list(getattr(res, "handovers", None) or [])
    flows = list(getattr(res, "flows", None) or [])
    if not flows:
        return compute_dead_seconds([], [], hops, recover_frac=recover_frac)
    fl = flows[0]
    t = list(getattr(fl, "t", None) or [])
    gp = list(getattr(fl, "goodput_bps", None) or [])
    return compute_dead_seconds(t, gp, hops, recover_frac=recover_frac)


def row_dead_sec_fields(detail: dict[str, Any] | None) -> dict[str, Any]:
    """Compact per-row stamps for eval JSON (full hop list stays optional)."""
    if not detail:
        return {
            "dead_s_mean": None,
            "dead_s_median": None,
            "dead_s_n_hops": 0,
            "dead_s_n_censored": 0,
            "dead_s_recover_frac": DEAD_SEC_RECOVER_FRAC,
        }
    return {
        "dead_s_mean": detail.get("dead_s_mean"),
        "dead_s_median": detail.get("dead_s_median"),
        "dead_s_n_hops": int(detail.get("n_hops") or 0),
        "dead_s_n_censored": int(detail.get("n_censored") or 0),
        "dead_s_recover_frac": float(
            detail.get("recover_frac", DEAD_SEC_RECOVER_FRAC)
        ),
    }


def dead_seconds_summary(rows: list[dict]) -> dict[str, Any]:
    """Aggregate row-level dead-second stamps into the eval summary block."""
    means = [
        float(r["dead_s_mean"])
        for r in rows
        if r.get("dead_s_mean") is not None
    ]
    n_hops = sum(int(r.get("dead_s_n_hops") or 0) for r in rows)
    n_cens = sum(int(r.get("dead_s_n_censored") or 0) for r in rows)
    fracs = [
        float(r["dead_s_recover_frac"])
        for r in rows
        if r.get("dead_s_recover_frac") is not None
    ]
    recover_frac = fracs[0] if fracs else DEAD_SEC_RECOVER_FRAC
    return {
        "metric": DEAD_SEC_METRIC,
        "recover_frac": recover_frac,
        "recover_pct": int(round(recover_frac * 100)),
        "definition": (
            f"seconds after detected RttHop until goodput recovers to "
            f"{recover_frac:.0%} of pre-hop epoch median goodput"
        ),
        "n_rows_with_metric": len(means),
        "n_hops_total": n_hops,
        "n_censored_total": n_cens,
        "dead_s_mean": round(_mean(means), 6) if means else None,
        "dead_s_median": round(_median(means), 6) if means else None,
        "soft_reprobe_cut": 0.58,
        "note": (
            "Observe-only efficacy surface. SoftReprobe cut 0.58 held. "
            "Not a dish Mbps claim."
        ),
    }
