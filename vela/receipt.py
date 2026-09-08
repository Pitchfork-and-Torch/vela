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


def build_receipt(
    *,
    source: str,
    source_name: str,
    compose: list[str],
    config: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    rows = list(summary.get("rows") or [])
    leaves = [row_digest(r) for r in rows]
    body = {
        "vela": __version__,
        "alg": "sha256",
        "domain": "VELA1",
        "source_name": source_name,
        "source_digest": source_digest(source),
        "compose": list(compose),
        "compose_digest": compose_digest(compose),
        "config_digest": config_digest(config),
        "n_rows": len(rows),
        "rows_merkle": merkle(leaves),
        "verdict": summary.get("verdict"),
        "power": summary.get("power"),
        "honesty": summary.get("honesty"),
    }
    body["receipt_digest"] = tagged("receipt", _canon(body))
    return body


def verify_receipt(receipt: dict[str, Any], *, source: str | None = None) -> list[str]:
    errs: list[str] = []
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
    return errs


def write_receipt(receipt: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8", newline="\n")
    return path


def _canon(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
