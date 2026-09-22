"""Fail-closed statistical badges.

`report ci` is sample mean +/- sample std. A p-value or a bootstrap
is not emitted, even when n >= 8. Receipts stamp that refusal.
This module does not retune SoftReprobe and does not claim dish Mbps.
"""
from __future__ import annotations

import re
from typing import Any

from vela.ir import parse_report_ci

STATS_METHOD = "mean+/-std"
P_VALUE_REFUSED = "refused"

# Whole tokens only. `p95` and `p_ho` are not p-values.
_BADGE_TOKENS = frozenset(
    {
        "p",
        "pvalue",
        "p_value",
        "p-value",
        "bootstrap",
        "paired_bootstrap",
        "paired-bootstrap",
        "significance",
        "ttest",
        "t_test",
        "t-test",
    }
)
# Digits stay on the token so p95 is not read as a bare p.
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*")
_SUMMARY_BADGE_KEYS = (
    "p_value",
    "pvalue",
    "p-value",
    "bootstrap",
    "significance",
    "t_test",
    "t-test",
)


def badge_error(contract: str, item: str) -> str:
    return (
        f"contract {contract}: p-value/bootstrap badge {item!r} is refused "
        f"(stats={STATS_METHOD}; coverage is not claimed)"
    )


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN.finditer(str(text))}


def _is_ci_report(item: str) -> bool:
    text = str(item).strip().lower()
    return text == "ci" or text.startswith("ci(")


def _is_badge(text: str) -> bool:
    return bool(_tokens(text) & _BADGE_TOKENS)


def badge_errors(con) -> list[str]:
    """Type errors for a contract that asks for a p-value or bootstrap."""
    errs: list[str] = []
    for item in list(getattr(con, "reports", []) or []):
        if _is_ci_report(item):
            continue
        if _is_badge(item):
            errs.append(badge_error(con.name, str(item)))
    for assertion in list(getattr(con, "asserts", []) or []):
        left = str(getattr(assertion, "left", "") or "")
        if _is_badge(left):
            errs.append(badge_error(con.name, left))
    return errs


def stats_stamp(con) -> str:
    """`mean+/-std` when `report ci` parses. Empty when CI was not asked."""
    level, ci_errs = parse_report_ci(list(getattr(con, "reports", []) or []))
    if level is None or ci_errs:
        return ""
    return STATS_METHOD


def summary_claims_badge(summary: dict | None) -> bool:
    """True when an eval object carries a p-value or a bootstrap method."""
    if not isinstance(summary, dict):
        return False
    for key in _SUMMARY_BADGE_KEYS:
        if key not in summary:
            continue
        val = summary[key]
        if val in (None, False, P_VALUE_REFUSED, STATS_METHOD):
            continue
        return True
    ci = summary.get("ci")
    if isinstance(ci, dict):
        method = ci.get("method")
        if method not in (None, "", STATS_METHOD):
            return True
        if ci.get("bootstrap") not in (None, False):
            return True
    return False


def receipt_stats_errors(
    receipt: dict[str, Any] | None,
    summary: dict[str, Any] | None = None,
) -> list[str]:
    """Receipt must not certify a p-value. A bound summary cannot smuggle one."""
    errs: list[str] = []
    if not isinstance(receipt, dict):
        return errs
    if receipt.get("p_value", P_VALUE_REFUSED) != P_VALUE_REFUSED:
        errs.append(f"p-value badge is refused (stats={STATS_METHOD})")
    if receipt.get("stats_method", STATS_METHOD) != STATS_METHOD:
        errs.append(f"stats_method must be {STATS_METHOD} (not a bootstrap)")
    if summary_claims_badge(summary):
        errs.append(
            "eval summary claims a p-value or bootstrap; receipt refuses that badge"
        )
    return errs
