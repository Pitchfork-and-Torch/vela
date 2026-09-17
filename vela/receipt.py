"""Eval receipts: a verdict is not a sentence, it is a commitment."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vela import __version__
from vela.digest import (
    compose_digest,
    config_digest,
    merkle,
    row_digest,
    source_digest,
    tagged,
)
from vela.path import path_digest

# House DualGate rails (EVAL-NOTES). --fast is not this gate.
HOUSE_GATE_SEEDS = frozenset({13, 7, 42, 99, 123})
HOUSE_GATE_DURATION_S = 90.0
HOUSE_GATE_SCENARIOS = frozenset({"leo_fast_ho", "terrestrial"})
FAST_GATE_SEEDS = frozenset({13, 7})
FAST_GATE_DURATION_S = 45.0


def eval_gate(
    seeds: list | None,
    duration_s: float | None,
    scenarios: list | None,
) -> str:
    """Label the run that produced the numbers. Not a dual-gate win."""
    got = {int(s) for s in (seeds or [])}
    scens = set(scenarios or [])
    dur = float(duration_s) if duration_s is not None else 0.0
    if (
        got == HOUSE_GATE_SEEDS
        and abs(dur - HOUSE_GATE_DURATION_S) < 1e-9
        and HOUSE_GATE_SCENARIOS <= scens
    ):
        return "house"
    if (
        got
        and got <= FAST_GATE_SEEDS
        and abs(dur - FAST_GATE_DURATION_S) < 1e-9
        and HOUSE_GATE_SCENARIOS <= scens
    ):
        return "fast"
    return "named"


def resolve_eval_rails(
    *,
    fast: bool = False,
    seeds: list[int] | None = None,
    duration_s: float | None = None,
) -> tuple[list[int] | None, float | None, list[str] | None, list[str]]:
    """CLI rails. --fast is a lock: it cannot become the house gate."""
    if fast and (seeds is not None or duration_s is not None):
        return None, None, None, [
            "--fast is the 45s two-seed path; drop --seeds/--duration "
            "(house rails with --fast is a mislabel)"
        ]
    if fast:
        return (
            sorted(FAST_GATE_SEEDS, reverse=True),
            FAST_GATE_DURATION_S,
            ["leo_fast_ho", "terrestrial"],
            [],
        )
    return seeds, duration_s, None, []


def gate_cli_line(gate: str, verdict: str | None = None) -> str:
    """One honest CLI line. ACCEPT on gate=fast is not a house win."""
    if gate == "house":
        line = "gate=house  (5 seeds, 90s, leo_fast_ho+terrestrial)"
    elif gate == "fast":
        line = "gate=fast  (not the house gate)"
    else:
        line = f"gate={gate}  (not the house gate)"
    if verdict == "ACCEPT" and gate != "house":
        line += ". ACCEPT here is not a dual-gate win"
    return line


def rows_merkle(rows: list[dict]) -> str:
    return merkle([row_digest(r) for r in rows])


def build_receipt(
    *,
    source: str,
    source_name: str,
    compose: list[str],
    config: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    rows = list(summary.get("rows") or [])
    body = {
        "vela": __version__,
        "alg": "sha256",
        "domain": "VELA1",
        "source_name": source_name,
        "source_digest": source_digest(source),
        "compose": list(compose),
        "compose_digest": compose_digest(compose),
        "config_digest": config_digest(config),
        "paths": list(config.get("paths") or []),
        "path_digest": config.get("path_digest") or path_digest(config.get("paths") or []),
        "n_rows": len(rows),
        "rows_merkle": rows_merkle(rows),
        "verdict": summary.get("verdict"),
        "power": summary.get("power"),
        "honesty": summary.get("honesty"),
        "gate": summary.get("gate") or eval_gate(
            config.get("seeds"),
            config.get("duration_s"),
            config.get("scenarios"),
        ),
    }
    body["receipt_digest"] = tagged("receipt", _canon(body))
    return body


def verify_receipt(
    receipt: dict[str, Any],
    *,
    source: str | None = None,
    config: dict[str, Any] | None = None,
    rows: list | None = None,
    summary: dict[str, Any] | None = None,
) -> list[str]:
    """Self-check the receipt. Bind source / config / rows when provided.

    A swapped goodput only fails when rows (or an eval summary) are bound.
    `vela receipt --source` alone cannot see the numbers.
    """
    errs: list[str] = []
    if not isinstance(receipt, dict):
        errs.append("receipt is not a JSON object")
        return errs
    if summary is not None and not isinstance(summary, dict):
        errs.append("eval summary is not a JSON object")
        return errs
    if receipt.get("domain") != "VELA1" or receipt.get("alg") != "sha256":
        errs.append("unknown receipt suite")
        return errs
    clone = {k: v for k, v in receipt.items() if k != "receipt_digest"}
    expect = tagged("receipt", _canon(clone))
    if receipt.get("receipt_digest") != expect:
        errs.append("receipt_digest mismatch (tampered or non-canonical)")
    if source is not None:
        got = source_digest(source)
        if got != receipt.get("source_digest"):
            errs.append("source_digest does not match provided source")
    if receipt.get("compose") is not None:
        cd = compose_digest(list(receipt["compose"]))
        if cd != receipt.get("compose_digest"):
            errs.append("compose_digest does not match compose list")
    if receipt.get("paths") is not None or receipt.get("path_digest"):
        pd = path_digest(list(receipt.get("paths") or []))
        if pd != receipt.get("path_digest"):
            errs.append("path_digest does not match paths")
    if summary is not None:
        if config is None and summary.get("config") is not None:
            config = summary.get("config")
        if rows is None and "rows" in summary:
            rows = list(summary.get("rows") or [])
        for key in ("verdict", "power", "honesty", "gate"):
            if key in receipt and key in summary and receipt.get(key) != summary.get(key):
                errs.append(f"{key} does not match eval")
    if config is not None:
        cd = config_digest(config)
        if cd != receipt.get("config_digest"):
            errs.append("config_digest does not match provided config")
        if receipt.get("gate"):
            expect_gate = eval_gate(
                config.get("seeds"),
                config.get("duration_s"),
                config.get("scenarios"),
            )
            if receipt.get("gate") != expect_gate:
                errs.append("gate does not match config seeds/duration/scenarios")
    if rows is not None:
        got_merkle = rows_merkle(list(rows))
        if got_merkle != receipt.get("rows_merkle"):
            errs.append("rows_merkle does not match provided rows")
        if int(receipt.get("n_rows") or 0) != len(rows):
            errs.append("n_rows does not match provided rows")
    return errs


def write_receipt(receipt: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8", newline="\n")
    return path


def _canon(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
