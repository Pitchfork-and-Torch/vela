"""Path law: the declared model is the one the sim runs.

A `path` block is not a comment. Check parses it, eval binds the
handover rails the sibling sim actually takes, and the receipt
commits the declared law. Calendar `p_ho` still comes from past
gaps. CSV traces stay unwired.

Honesty: LeoPath / LeoFastHO rails are Starlink-class lab models,
not an orbit or cell replay. Check stamps `sim!=orbit` so a mix of
from_csv with parametric rails, or an orbit/cell/replay claim from
lab rails, cannot pass unlabeled.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from vela.ast import PathModel
from vela.digest import tagged
from vela.types import KNOWN_SCENARIOS

PATH_FIELDS = frozenset(
    {"handover", "rtt_jump", "capacity", "mobility_loss", "honesty", "from_csv"}
)
PARAMETRIC_PATH_FIELDS = frozenset(
    {"handover", "rtt_jump", "capacity", "mobility_loss"}
)
# from_csv is recognized for honesty / mix detection only on this cook.
# Full CSV PathModel wiring stays on open PR #48; we do not load traces here.
SIM_NE_ORBIT = "sim!=orbit"

# Program name -> contract scenario. Unmapped names stay unbound.
PATH_SCENARIO = {
    "LeoFastHO": "leo_fast_ho",
    "leo_fast_ho": "leo_fast_ho",
    "LeoSingle": "leo_single",
    "leo_single": "leo_single",
    "Terrestrial": "terrestrial",
    "terrestrial": "terrestrial",
    "LeoMulti": "leo_multi",
    "leo_multi": "leo_multi",
}

# House leo_fast_ho rails. Flagship examples already write these.
HOUSE_HANDOVER_INTERVAL_S = 12.0
HOUSE_HANDOVER_JITTER_S = 4.0

_NUM = r"([0-9]+(?:\.[0-9]+)?)"
_HANDOVER = re.compile(
    rf"^every\s+{_NUM}(ms|s)\s+jitter\s+{_NUM}(ms|s)$",
    re.IGNORECASE,
)
_UNIFORM = re.compile(
    rf"^uniform\s+{_NUM}(ms|s|mbps|kbps|bps)\s+{_NUM}(ms|s|mbps|kbps|bps)$",
    re.IGNORECASE,
)
_BURST = re.compile(
    rf"^burst\s+p\s*=\s*{_NUM}\s+window\s*=?\s*{_NUM}(ms|s)$",
    re.IGNORECASE,
)


def _to_seconds(value: str, unit: str) -> float:
    n = float(value)
    u = unit.lower()
    if u == "ms":
        return n / 1000.0
    if u == "s":
        return n
    raise ValueError(f"not a time unit: {unit}")


def _to_bps(value: str, unit: str) -> float:
    n = float(value)
    u = unit.lower()
    if u == "mbps":
        return n * 1e6
    if u == "kbps":
        return n * 1e3
    if u == "bps":
        return n
    raise ValueError(f"not a rate unit: {unit}")


@dataclass
class PathLaw:
    name: str
    scenario: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    handover_interval_s: float | None = None
    handover_jitter_s: float | None = None
    rtt_jump_lo_s: float | None = None
    rtt_jump_hi_s: float | None = None
    capacity_lo_bps: float | None = None
    capacity_hi_bps: float | None = None
    mobility_p: float | None = None
    mobility_window_s: float | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def bound(self) -> bool:
        return bool(self.scenario) and self.handover_interval_s is not None

    @property
    def house(self) -> bool:
        return (
            self.scenario == "leo_fast_ho"
            and self.handover_interval_s is not None
            and self.handover_jitter_s is not None
            and abs(self.handover_interval_s - HOUSE_HANDOVER_INTERVAL_S) < 1e-9
            and abs(self.handover_jitter_s - HOUSE_HANDOVER_JITTER_S) < 1e-9
        )

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "scenario": self.scenario,
            "handover_interval_s": self.handover_interval_s,
            "handover_jitter_s": self.handover_jitter_s,
            "fields": dict(self.fields),
        }

    def stamp(self) -> str:
        honesty = f" {SIM_NE_ORBIT}" if path_needs_sim_ne_orbit(self) else ""
        if "from_csv" in self.fields and self.handover_interval_s is None:
            scen = self.scenario or "unbound"
            return f"{self.name}:{scen} from_csv (lab){honesty}"
        if self.handover_interval_s is None:
            return f"{self.name}  (unbound){honesty}"
        jitter = self.handover_jitter_s
        jtxt = f"+/-{jitter:g}s" if jitter is not None else ""
        rail = "house" if self.house else "named"
        scen = self.scenario or "unbound"
        return f"{self.name}:{scen} {self.handover_interval_s:g}s{jtxt} ({rail}){honesty}"


def path_needs_std_error() -> str:
    return "path requires `use std.path` (same model as the sim; not a comment)"


def path_unknown_field_error(name: str, field: str) -> str:
    known = ", ".join(sorted(PATH_FIELDS))
    return f"path {name}: unknown field {field} (known: {known})"


def path_parse_error(name: str, field: str) -> str:
    return f"path {name}: cannot parse {field} (path law)"


def path_empty_error(name: str) -> str:
    return f"path {name}: empty model (path law; a claim needs rails)"


def parse_path_model(model: PathModel) -> PathLaw:
    law = PathLaw(name=model.name, fields=dict(model.fields))
    law.scenario = PATH_SCENARIO.get(model.name, "")
    if not model.fields:
        law.errors.append(path_empty_error(model.name))
        return law
    for key, raw in model.fields.items():
        if key not in PATH_FIELDS:
            law.errors.append(path_unknown_field_error(model.name, key))
            continue
        if key == "honesty":
            # Free-text label; sim!=orbit acknowledges lab != orbit.
            continue
        if key == "from_csv":
            # Honesty surface only; do not load CSV bytes (see PR #48).
            continue
        text = " ".join(
            str(raw).replace("(", " ").replace(")", " ").replace(",", " ").split()
        )
        if key == "handover":
            m = _HANDOVER.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                law.handover_interval_s = _to_seconds(m.group(1), m.group(2))
                law.handover_jitter_s = _to_seconds(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(path_parse_error(model.name, key))
        elif key == "rtt_jump":
            m = _UNIFORM.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                law.rtt_jump_lo_s = _to_seconds(m.group(1), m.group(2))
                law.rtt_jump_hi_s = _to_seconds(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(path_parse_error(model.name, key))
        elif key == "capacity":
            m = _UNIFORM.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                law.capacity_lo_bps = _to_bps(m.group(1), m.group(2))
                law.capacity_hi_bps = _to_bps(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(path_parse_error(model.name, key))
        elif key == "mobility_loss":
            m = _BURST.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            p = float(m.group(1))
            if not (0.0 <= p <= 1.0):
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                law.mobility_p = p
                law.mobility_window_s = _to_seconds(m.group(2), m.group(3))
            except ValueError:
                law.errors.append(path_parse_error(model.name, key))
    return law


def parse_program_paths(models: list[PathModel]) -> list[PathLaw]:
    return [parse_path_model(m) for m in models]


def path_digest(laws: list[PathLaw] | list[dict]) -> str:
    rows: list[dict] = []
    for item in laws:
        if isinstance(item, PathLaw):
            rows.append(item.as_dict())
        else:
            rows.append(
                {
                    "name": item.get("name", ""),
                    "scenario": item.get("scenario", ""),
                    "handover_interval_s": item.get("handover_interval_s"),
                    "handover_jitter_s": item.get("handover_jitter_s"),
                    "fields": dict(item.get("fields") or {}),
                }
            )
    blob = "|".join(
        [
            f"{r.get('name','')}:{r.get('scenario','')}:"
            f"{r.get('handover_interval_s')}:{r.get('handover_jitter_s')}:"
            + ",".join(f"{k}={v}" for k, v in sorted((r.get("fields") or {}).items()))
            for r in rows
        ]
    )
    return tagged("path", blob or "empty")


def path_overlay(
    scenario: str, cfg
) -> tuple[float | None, float | None]:
    """Handover rails declared for this scenario, or (None, None)."""
    if cfg is None:
        return None, None
    for item in getattr(cfg, "paths", None) or []:
        if isinstance(item, dict) and item.get("scenario") == scenario:
            return item.get("handover_interval_s"), item.get("handover_jitter_s")
    if getattr(cfg, "path_scenario", "") == scenario:
        return (
            getattr(cfg, "handover_interval_s", None),
            getattr(cfg, "handover_jitter_s", None),
        )
    return None, None


def has_honesty_label(law: PathLaw) -> bool:
    """True when the path block already labels sim!=orbit."""
    raw = str(law.fields.get("honesty", "")).lower()
    compact = raw.replace(" ", "")
    return SIM_NE_ORBIT in compact or "sim!=orbit" in compact


def path_claims_orbit_replay(law: PathLaw) -> bool:
    """Name looks like an orbit/cell replay claim from lab rails."""
    n = law.name.lower()
    return any(tok in n for tok in ("orbit", "cell", "replay"))


def path_mixes_csv_parametric(law: PathLaw) -> bool:
    """from_csv plus LeoFastHO parametric rails in one path block."""
    has_csv = "from_csv" in law.fields
    has_param = bool(PARAMETRIC_PATH_FIELDS & set(law.fields))
    return has_csv and has_param


def path_needs_sim_ne_orbit(law: PathLaw) -> bool:
    """Stamp when lab rails must not be read as orbit/cell replay."""
    is_leo = bool(law.scenario) and str(law.scenario).startswith("leo_")
    return bool(
        is_leo
        or path_claims_orbit_replay(law)
        or path_mixes_csv_parametric(law)
        or "from_csv" in law.fields
    )


def sim_ne_orbit_warning(law: PathLaw) -> str | None:
    """Warn/stamp sim!=orbit for unlabeled mix or orbit-claim lab rails.

    SoftReprobe cut stays 0.58. Observe-only. No dish Mbps claim.
    """
    mix = path_mixes_csv_parametric(law)
    labeled = has_honesty_label(law)
    if labeled:
        return None
    if mix:
        return (
            f"{SIM_NE_ORBIT}: path {law.name} mixes from_csv with "
            "LeoFastHO parametric rails without honesty label "
            "(lab != orbit; not a cell replay)"
        )
    if "from_csv" in law.fields:
        return (
            f"{SIM_NE_ORBIT}: path {law.name} from_csv is lab replay "
            "(not orbit; not a dish Mbps claim)"
        )
    if path_claims_orbit_replay(law):
        return (
            f"{SIM_NE_ORBIT}: path {law.name} claims orbit/cell replay "
            "from lab rails (LeoPath is Starlink-class, not a cell replay)"
        )
    is_leo = bool(law.scenario) and str(law.scenario).startswith("leo_")
    if is_leo:
        return (
            f"{SIM_NE_ORBIT}: path {law.name} LeoPath is Starlink-class "
            "(not a cell replay; lab rails != orbit)"
        )
    return None


def house_mismatch_warning(law: PathLaw) -> str | None:
    if law.scenario != "leo_fast_ho" or not law.bound or law.house:
        return None
    return (
        f"path {law.name}: leo_fast_ho handover "
        f"{law.handover_interval_s:g}s+/-{law.handover_jitter_s:g}s "
        f"is not the house {HOUSE_HANDOVER_INTERVAL_S:g}s+/-"
        f"{HOUSE_HANDOVER_JITTER_S:g}s rail"
    )


def unbound_path_warning(law: PathLaw) -> str | None:
    if law.scenario:
        return None
    known = ", ".join(sorted(KNOWN_SCENARIOS))
    return (
        f"path {law.name}: name does not bind a known scenario "
        f"({known}); eval keeps house defaults"
    )
