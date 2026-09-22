"""Optional LeoAware std.mech declaration wire.

Cites / validates VELA ``std.mech`` against the sibling gift surface::

    python3 -m leo_cc.mech_decl   # schema leoaware.vela_std_mech/v1

Rules
-----
- Do not fork Detect / SoftReprobe. SoftReprobe house cut stays 0.58.
- Do not enable closed-write on flagships.
- ``vela check`` on flagships must not require leo-aware-transport at runtime.
- Optional validate is fail-closed when the sibling is missing *and*
  validation was explicitly requested (``--against-leoaware``).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vela.kernel import leo_aware_root
from vela.types import HOUSE_ENDPOINT_CUT, STDLIB_MECHANISMS

# Cited LeoAware gift schema (Pitchfork-and-Torch/leo-aware-transport tip).
LEOAWARE_MECH_SCHEMA = "leoaware.vela_std_mech/v1"

# Names VELA composers share with the LeoAware gift export. Local-only
# mechanisms (Calendar, QuietReach, ...) stay VELA-side.
GIFT_MECH_NAMES = frozenset(
    {
        "Detect",
        "SoftReprobe",
        "OCE",
        "DualGateGuard",
        "SoftFlicker",
        "TypedLoss",
        "IntervalBw",
    }
)

REQUIRED_OBSERVE_HOOKS = frozenset(
    {
        "handover_flicker_hook",
        "classify_handover_flicker",
    }
)


class MechDeclError(Exception):
    """Fail-closed LeoAware declaration wire error."""


@dataclass
class MechDeclReport:
    ok: bool
    sibling_present: bool
    schema: str = ""
    package_version: str = ""
    endpoint_cut: float | None = None
    shared: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cite: str = ""

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise MechDeclError("; ".join(self.errors) or "mech_decl validation failed")


def sibling_present(root: Path | None = None) -> bool:
    """True when leo-aware-transport is on disk with leo_cc.mech_decl."""
    p = root if root is not None else leo_aware_root()
    try:
        return (
            p.is_dir()
            and (p / "leo_cc").is_dir()
            and (p / "leo_cc" / "mech_decl.py").is_file()
        )
    except OSError:
        return False


def load_leoaware_decl(
    *, root: Path | None = None, require: bool = True
) -> dict[str, Any]:
    """Load ``leoaware.vela_std_mech/v1`` from the sibling tree.

    When ``require`` is True (default), missing sibling is fail-closed.
    When False, returns ``{}`` if absent (caller may skip).
    """
    p = root if root is not None else leo_aware_root()
    if not sibling_present(p):
        if require:
            raise MechDeclError(
                f"leo-aware-transport sibling missing at {p} "
                "(set LEO_AWARE_TRANSPORT or place sibling next to vela)"
            )
        return {}
    root_s = str(p)
    # Prefer sibling import without permanently mutating a poisoned path.
    inserted = False
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
        inserted = True
    try:
        # Drop a stale leo_cc if another tree was imported earlier this process.
        for mod in list(sys.modules):
            if mod == "leo_cc" or mod.startswith("leo_cc."):
                del sys.modules[mod]
        from leo_cc.mech_decl import mechanism_declaration  # type: ignore
    except Exception as exc:  # noqa: BLE001 - surface import failure clearly
        raise MechDeclError(f"cannot import leo_cc.mech_decl from {p}: {exc}") from exc
    finally:
        if inserted and sys.path and sys.path[0] == root_s:
            # Leave on path so subsequent leo_cc use in-process still works;
            # only remove if we want strict isolation. Keep inserted.
            pass
    decl = mechanism_declaration()
    if not isinstance(decl, dict):
        raise MechDeclError(
            "leo_cc.mech_decl.mechanism_declaration() did not return a dict"
        )
    return decl


def cite_leoaware_surface(decl: dict[str, Any] | None = None) -> str:
    """One-line cite for docs / `vela mech` / optional check stamp."""
    if decl is None:
        return (
            f"cite {LEOAWARE_MECH_SCHEMA} "
            f"(Detect/SoftReprobe/OCE/DualGateGuard/SoftFlicker/TypedLoss; "
            f"SoftReprobe cut {HOUSE_ENDPOINT_CUT}; observe handover_flicker_hook)"
        )
    schema = str(decl.get("schema") or LEOAWARE_MECH_SCHEMA)
    house = decl.get("house") or {}
    cut = house.get("endpoint_cut", HOUSE_ENDPOINT_CUT)
    ver = decl.get("package_version") or "?"
    return (
        f"cite {schema} @ leo-aware-transport {ver}; "
        f"SoftReprobe house cut {cut}; observe handover_flicker_hook"
    )


def _as_set(xs: Any) -> set[str]:
    if xs is None:
        return set()
    if isinstance(xs, (set, frozenset, list, tuple)):
        return {str(x) for x in xs}
    return {str(xs)}


def validate_stdlib_against_decl(decl: dict[str, Any]) -> MechDeclReport:
    """Compare VELA STDLIB_MECHANISMS to a loaded LeoAware declaration."""
    report = MechDeclReport(ok=True, sibling_present=True)
    schema = str(decl.get("schema") or "")
    report.schema = schema
    report.package_version = str(decl.get("package_version") or "")
    if schema != LEOAWARE_MECH_SCHEMA:
        report.ok = False
        report.errors.append(
            f"schema {schema!r} != cited {LEOAWARE_MECH_SCHEMA!r}"
        )

    house = decl.get("house") or {}
    cut_raw = house.get("endpoint_cut")
    try:
        cut = float(cut_raw) if cut_raw is not None else None
    except (TypeError, ValueError):
        cut = None
    report.endpoint_cut = cut
    if cut is None or abs(cut - HOUSE_ENDPOINT_CUT) > 1e-9:
        report.ok = False
        report.errors.append(
            f"house endpoint_cut {cut_raw!r} must equal VELA SoftReprobe "
            f"HOUSE_ENDPOINT_CUT {HOUSE_ENDPOINT_CUT}"
        )

    std = decl.get("std_mech") or {}
    if not isinstance(std, dict) or not std:
        report.ok = False
        report.errors.append("decl.std_mech missing or empty")
        report.cite = cite_leoaware_surface(decl)
        return report

    missing_gift = sorted(GIFT_MECH_NAMES - set(std))
    if missing_gift:
        report.ok = False
        report.errors.append(
            f"LeoAware gift missing mechanisms: {', '.join(missing_gift)}"
        )

    hooks = _as_set(decl.get("observe_hooks"))
    missing_hooks = sorted(REQUIRED_OBSERVE_HOOKS - hooks)
    if missing_hooks:
        report.ok = False
        report.errors.append(
            f"observe hooks missing {', '.join(missing_hooks)} "
            "(handover_flicker_hook is observe-only; do not ship SoftFlicker as flagship)"
        )

    shared = sorted(set(std) & set(STDLIB_MECHANISMS) & GIFT_MECH_NAMES)
    report.shared = shared
    for name in shared:
        leo = std[name]
        vela = STDLIB_MECHANISMS[name]
        if not isinstance(leo, dict):
            report.ok = False
            report.errors.append(f"{name}: LeoAware entry is not an object")
            continue
        for key in ("reads", "writes"):
            if _as_set(leo.get(key)) != _as_set(vela.get(key)):
                report.ok = False
                report.errors.append(
                    f"{name}.{key}: LeoAware {_as_set(leo.get(key))} != "
                    f"VELA {_as_set(vela.get(key))} (do not fork)"
                )
        leo_cuts = str(leo.get("cuts", "none"))
        vela_cuts = str(vela.get("cuts", "none"))
        if leo_cuts != vela_cuts:
            report.ok = False
            report.errors.append(
                f"{name}.cuts: LeoAware {leo_cuts!r} != VELA {vela_cuts!r}"
            )
        leo_phase = str(leo.get("phase", "ack"))
        vela_phase = str(vela.get("phase", "ack"))
        if leo_phase != vela_phase:
            report.ok = False
            report.errors.append(
                f"{name}.phase: LeoAware {leo_phase!r} != VELA {vela_phase!r}"
            )
        if name == "SoftReprobe":
            leo_side = leo.get("leoaware") or {}
            hcut = leo_side.get("house_endpoint_cut")
            try:
                hcut_f = float(hcut) if hcut is not None else None
            except (TypeError, ValueError):
                hcut_f = None
            if hcut_f is None or abs(hcut_f - HOUSE_ENDPOINT_CUT) > 1e-9:
                report.ok = False
                report.errors.append(
                    f"SoftReprobe.leoaware.house_endpoint_cut {hcut!r} "
                    f"must stay {HOUSE_ENDPOINT_CUT} (do not retune)"
                )

    gift = decl.get("gift_compose") or {}
    reach = gift.get("Reach_flagship") if isinstance(gift, dict) else None
    if isinstance(reach, dict):
        compose = list(reach.get("compose") or [])
        posture = str(reach.get("posture") or "")
        if set(compose) != {"Detect", "SoftReprobe"}:
            report.warnings.append(
                f"Reach_flagship compose {compose} — cite Detect+SoftReprobe observe"
            )
        if posture and posture != "observe":
            report.ok = False
            report.errors.append(
                f"Reach_flagship posture {posture!r} must be observe "
                "(do not enable closed-write on flagship)"
            )

    report.cite = cite_leoaware_surface(decl)
    return report


def validate_against_leoaware(
    *,
    root: Path | None = None,
    require_sibling: bool = True,
) -> MechDeclReport:
    """Validate VELA std.mech against sibling LeoAware gift.

    ``require_sibling=True`` (CLI ``--against-leoaware``): fail-closed if missing.
    ``require_sibling=False``: report sibling_present=False so tests can skip.
    """
    p = root if root is not None else leo_aware_root()
    if not sibling_present(p):
        msg = (
            f"leo-aware-transport sibling missing at {p} "
            "(fail-closed for --against-leoaware; tests should skip)"
        )
        return MechDeclReport(
            ok=False,
            sibling_present=False,
            errors=[msg],
            cite=cite_leoaware_surface(None),
        )
    try:
        decl = load_leoaware_decl(root=p, require=True)
    except MechDeclError as exc:
        return MechDeclReport(
            ok=False,
            sibling_present=True,
            errors=[str(exc)],
            cite=cite_leoaware_surface(None),
        )
    report = validate_stdlib_against_decl(decl)
    if require_sibling and not report.ok:
        return report
    return report


def dump_cite_json(decl: dict[str, Any] | None = None) -> str:
    """Compact JSON cite for tooling."""
    payload: dict[str, Any] = {
        "schema": LEOAWARE_MECH_SCHEMA,
        "house_endpoint_cut": HOUSE_ENDPOINT_CUT,
        "gift_mechs": sorted(GIFT_MECH_NAMES),
        "observe_hooks_required": sorted(REQUIRED_OBSERVE_HOOKS),
        "closed_write": False,
        "cite": cite_leoaware_surface(decl),
    }
    if decl:
        payload["leoaware_package_version"] = decl.get("package_version")
        payload["leoaware_schema"] = decl.get("schema")
    return json.dumps(payload, indent=2, sort_keys=True)
