"""Flicker dead-ms: Starlink mid-epoch efficacy (observe-only).

Flicker is not RttHop. PR #46 stamps hop dead_seconds after handover;
this module measures a separate arm: time after a mid-epoch Flicker
capacity step until goodput recovers to RECOVER_FRAC of the pre-event
epoch median, reported in milliseconds as flicker_dead_ms.

SoftReprobe cut stays 0.58 on both hop and flicker. No Detect/SoftReprobe
fork. No closed-write. No dish Mbps claim.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

# Same recover law as hop dead-seconds; units differ (ms vs s).
FLICKER_DEAD_RECOVER_FRAC = 0.80
FLICKER_DEAD_METRIC = "flicker_dead_ms"
FLICKER_EVENT_KIND = "Flicker"
FLICKER_NOT_HOP_LABEL = "Flicker; not RttHop"
# Drop flicker marks that sit on a handover (sibling may log both edges).
HOP_COINCIDE_EPS_S = 0.05
SOFT_REPROBE_CUT = 0.58


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


def _p95(xs: list[float]) -> float:
    """Nearest-rank p95. Empty -> nan."""
    if not xs:
        return float("nan")
    ys = sorted(float(x) for x in xs)
    # ceil(0.95 * n) as 1-based rank, then index.
    rank = max(1, int(math.ceil(0.95 * len(ys))))
    return float(ys[rank - 1])


def _labels() -> dict[str, Any]:
    return {
        "event_kind": FLICKER_EVENT_KIND,
        "not_rtt_hop": True,
        "label": FLICKER_NOT_HOP_LABEL,
        "soft_reprobe_cut": SOFT_REPROBE_CUT,
        "vs_hop_metric": "dead_seconds_after_handover",
        "note": (
            "Flicker is mid-epoch capacity step (starlink_v2 / path.flicker). "
            "Not RttHop / handover. SoftReprobe cut 0.58 on both arms. "
            "Observe-only. No dish Mbps claim."
        ),
    }


def filter_flicker_times(
    flicker_times: Sequence[float],
    hop_times: Sequence[float] | None = None,
    *,
    eps_s: float = HOP_COINCIDE_EPS_S,
) -> list[float]:
    """Keep Flicker marks that are not coincident with RttHop."""
    hops = [float(h) for h in (hop_times or [])]
    out: list[float] = []
    for ft in sorted(float(x) for x in flicker_times):
        if any(abs(ft - h) <= eps_s for h in hops):
            continue
        out.append(ft)
    return out


def compute_flicker_dead_ms(
    t: Sequence[float],
    goodput_bps: Sequence[float],
    flicker_times: Sequence[float],
    *,
    hop_times: Sequence[float] | None = None,
    recover_frac: float = FLICKER_DEAD_RECOVER_FRAC,
    end_t: float | None = None,
) -> dict[str, Any]:
    """Measure dead milliseconds after each Flicker (not RttHop).

    Pre-event epoch for flicker F at f_i is [f_{i-1}, f_i) (or [t0, f_i)
    for the first). Threshold is recover_frac * pre-event median goodput.
    Dead ms = 1000 * (recover_t - f_i). Censored if recovery never hits
    before the next flicker (or end_t).
    """
    definition = (
        f"milliseconds after Flicker (not RttHop) until goodput recovers to "
        f"{recover_frac:.0%} of pre-event epoch median goodput"
    )
    out: dict[str, Any] = {
        "metric": FLICKER_DEAD_METRIC,
        "recover_frac": float(recover_frac),
        "recover_pct": int(round(float(recover_frac) * 100)),
        "definition": definition,
        "events": [],
        "n_flickers": 0,
        "n_recovered": 0,
        "n_censored": 0,
        "n_dropped_hop_coincide": 0,
        "flicker_dead_ms_mean": None,
        "flicker_dead_ms_median": None,
        "flicker_dead_ms_p95": None,
        "flicker_dead_ms_total": None,
        **_labels(),
    }
    raw = [float(x) for x in flicker_times]
    hops = [float(h) for h in (hop_times or [])]
    kept = filter_flicker_times(raw, hops)
    out["n_dropped_hop_coincide"] = len(raw) - len(kept)

    if not t or not goodput_bps or len(t) != len(goodput_bps):
        out["note"] = "empty or misaligned timeseries; " + str(out["note"])
        return out
    times = [float(x) for x in t]
    gps = [float(x) for x in goodput_bps]
    if not kept:
        out["note"] = (
            "no Flicker marks after hop-coincide filter; "
            + FLICKER_NOT_HOP_LABEL
        )
        return out

    t0 = times[0]
    t_end = float(end_t) if end_t is not None else times[-1]
    rows: list[dict[str, Any]] = []
    dead_ms_vals: list[float] = []
    for i, flick_t in enumerate(kept):
        prev = kept[i - 1] if i > 0 else t0
        nxt = kept[i + 1] if i + 1 < len(kept) else t_end
        pre = [gp for tt, gp in zip(times, gps) if prev <= tt < flick_t]
        if not pre:
            rows.append(
                {
                    "flicker_t": flick_t,
                    "event_kind": FLICKER_EVENT_KIND,
                    "not_rtt_hop": True,
                    "pre_event_median_bps": None,
                    "threshold_bps": None,
                    "recover_t": None,
                    "flicker_dead_ms": None,
                    "censored": True,
                    "note": "no pre-event samples",
                }
            )
            continue
        med = _median(pre)
        thr = float(recover_frac) * med
        recover_t = None
        for tt, gp in zip(times, gps):
            if tt < flick_t:
                continue
            if tt > nxt:
                break
            if gp >= thr:
                recover_t = tt
                break
        if recover_t is None:
            dead_s = max(0.0, float(nxt) - flick_t)
            censored = True
        else:
            dead_s = max(0.0, float(recover_t) - flick_t)
            censored = False
        dead_ms = round(dead_s * 1000.0, 3)
        rows.append(
            {
                "flicker_t": flick_t,
                "event_kind": FLICKER_EVENT_KIND,
                "not_rtt_hop": True,
                "label": FLICKER_NOT_HOP_LABEL,
                "pre_event_median_bps": med,
                "threshold_bps": thr,
                "recover_t": recover_t,
                "flicker_dead_ms": dead_ms,
                "censored": censored,
            }
        )
        dead_ms_vals.append(dead_ms)

    out["events"] = rows
    out["n_flickers"] = len(rows)
    out["n_recovered"] = sum(1 for r in rows if not r.get("censored"))
    out["n_censored"] = sum(1 for r in rows if r.get("censored"))
    if dead_ms_vals:
        out["flicker_dead_ms_mean"] = round(_mean(dead_ms_vals), 3)
        out["flicker_dead_ms_median"] = round(_median(dead_ms_vals), 3)
        out["flicker_dead_ms_p95"] = round(_p95(dead_ms_vals), 3)
        out["flicker_dead_ms_total"] = round(sum(dead_ms_vals), 3)
    return out


def flicker_times_from_sim(res: Any) -> list[float]:
    """Best-effort Flicker marks from a LeoAware SimResult.

    Sibling SimResult currently stamps handovers only; flicker_times may
    appear on the result or nested path/cfg when the sibling exposes them.
    Empty list is honest (house leo_fast_ho has no mid-epoch Flicker rail).
    """
    ft = getattr(res, "flicker_times", None)
    if ft is not None:
        return [float(x) for x in ft]
    path = getattr(res, "path", None)
    if path is not None:
        pft = getattr(path, "flicker_times", None)
        if pft is not None:
            return [float(x) for x in pft]
    cfg = getattr(res, "cfg", None)
    if cfg is not None:
        cft = getattr(cfg, "flicker_times", None)
        if cft is not None:
            return [float(x) for x in cft]
    return []


def flicker_dead_from_sim(
    res: Any, *, recover_frac: float = FLICKER_DEAD_RECOVER_FRAC
) -> dict[str, Any]:
    """Compute flicker_dead_ms from a leo-aware-transport SimResult (flow 0)."""
    hops = list(getattr(res, "handovers", None) or [])
    flickers = flicker_times_from_sim(res)
    flows = list(getattr(res, "flows", None) or [])
    if not flows:
        return compute_flicker_dead_ms(
            [], [], flickers, hop_times=hops, recover_frac=recover_frac
        )
    fl = flows[0]
    t = list(getattr(fl, "t", None) or [])
    gp = list(getattr(fl, "goodput_bps", None) or [])
    return compute_flicker_dead_ms(
        t, gp, flickers, hop_times=hops, recover_frac=recover_frac
    )


def row_flicker_dead_fields(detail: dict[str, Any] | None) -> dict[str, Any]:
    """Compact per-row stamps for eval JSON."""
    base = {
        "flicker_dead_ms_mean": None,
        "flicker_dead_ms_p95": None,
        "flicker_dead_ms_n": 0,
        "flicker_dead_ms_n_censored": 0,
        "flicker_dead_ms_recover_frac": FLICKER_DEAD_RECOVER_FRAC,
        "flicker_event_kind": FLICKER_EVENT_KIND,
        "flicker_not_rtt_hop": True,
        "flicker_label": FLICKER_NOT_HOP_LABEL,
    }
    if not detail:
        return base
    return {
        "flicker_dead_ms_mean": detail.get("flicker_dead_ms_mean"),
        "flicker_dead_ms_p95": detail.get("flicker_dead_ms_p95"),
        "flicker_dead_ms_n": int(detail.get("n_flickers") or 0),
        "flicker_dead_ms_n_censored": int(detail.get("n_censored") or 0),
        "flicker_dead_ms_recover_frac": float(
            detail.get("recover_frac", FLICKER_DEAD_RECOVER_FRAC)
        ),
        "flicker_event_kind": FLICKER_EVENT_KIND,
        "flicker_not_rtt_hop": True,
        "flicker_label": FLICKER_NOT_HOP_LABEL,
    }


def flicker_dead_summary(rows: list[dict]) -> dict[str, Any]:
    """Aggregate row-level flicker_dead_ms stamps into the eval summary block."""
    means = [
        float(r["flicker_dead_ms_mean"])
        for r in rows
        if r.get("flicker_dead_ms_mean") is not None
    ]
    p95s = [
        float(r["flicker_dead_ms_p95"])
        for r in rows
        if r.get("flicker_dead_ms_p95") is not None
    ]
    n_ev = sum(int(r.get("flicker_dead_ms_n") or 0) for r in rows)
    n_cens = sum(int(r.get("flicker_dead_ms_n_censored") or 0) for r in rows)
    fracs = [
        float(r["flicker_dead_ms_recover_frac"])
        for r in rows
        if r.get("flicker_dead_ms_recover_frac") is not None
    ]
    recover_frac = fracs[0] if fracs else FLICKER_DEAD_RECOVER_FRAC
    return {
        "metric": FLICKER_DEAD_METRIC,
        "recover_frac": recover_frac,
        "recover_pct": int(round(recover_frac * 100)),
        "definition": (
            f"milliseconds after Flicker (not RttHop) until goodput recovers to "
            f"{recover_frac:.0%} of pre-event epoch median goodput"
        ),
        "n_rows_with_metric": len(means),
        "n_flickers_total": n_ev,
        "n_censored_total": n_cens,
        "flicker_dead_ms_mean": round(_mean(means), 3) if means else None,
        "flicker_dead_ms_p95": round(_p95(means), 3) if means else (
            round(_p95(p95s), 3) if p95s else None
        ),
        **_labels(),
    }


def format_flicker_dead_cli(block: dict[str, Any] | None) -> str:
    """One ASCII CLI line for house / fast eval prints."""
    if not block:
        return (
            f"flicker_dead_ms  mean=n/a  p95=n/a  "
            f"({FLICKER_NOT_HOP_LABEL}; SoftReprobe {SOFT_REPROBE_CUT})"
        )
    mean = block.get("flicker_dead_ms_mean")
    p95 = block.get("flicker_dead_ms_p95")
    mean_s = f"{mean:.3f}" if isinstance(mean, (int, float)) else "n/a"
    p95_s = f"{p95:.3f}" if isinstance(p95, (int, float)) else "n/a"
    n = block.get("n_flickers_total", block.get("n_flickers", 0))
    return (
        f"flicker_dead_ms  mean={mean_s}  p95={p95_s}  n={n}  "
        f"({FLICKER_NOT_HOP_LABEL}; SoftReprobe {SOFT_REPROBE_CUT})"
    )
