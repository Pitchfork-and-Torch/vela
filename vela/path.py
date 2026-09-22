"""Path law: the declared model is the one the sim runs.

A `path` block is not a comment. Check parses it, eval binds the
handover rails the sibling sim actually takes, and the receipt
commits the declared law. Calendar `p_ho` still comes from past
gaps. CSV traces stay unwired.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from vela.ast import PathModel
from vela.digest import tagged
from vela.types import KNOWN_SCENARIOS

PATH_FIELDS = frozenset({"handover", "rtt_jump", "capacity", "mobility_loss"})

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
            "rtt_jump_lo_s": self.rtt_jump_lo_s,
            "rtt_jump_hi_s": self.rtt_jump_hi_s,
            "capacity_lo_bps": self.capacity_lo_bps,
            "capacity_hi_bps": self.capacity_hi_bps,
            "mobility_p": self.mobility_p,
            "mobility_window_s": self.mobility_window_s,
            "fields": dict(self.fields),
        }

    def stamp(self) -> str:
        if self.handover_interval_s is None:
            return f"{self.name}  (unbound)"
        jitter = self.handover_jitter_s
        jtxt = f"+/-{jitter:g}s" if jitter is not None else ""
        rail = "house" if self.house else "named"
        scen = self.scenario or "unbound"
        cap = ""
        if self.capacity_lo_bps is not None and self.capacity_hi_bps is not None:
            lo = self.capacity_lo_bps / 1e6
            hi = self.capacity_hi_bps / 1e6
            cap = f" {lo:g}-{hi:g}Mbps"
        return f"{self.name}:{scen} {self.handover_interval_s:g}s{jtxt}{cap} ({rail})"


def path_needs_std_error() -> str:
    return "path requires `use std.path` (same model as the sim; not a comment)"


def path_unknown_field_error(name: str, field: str) -> str:
    known = ", ".join(sorted(PATH_FIELDS))
    return f"path {name}: unknown field {field} (known: {known})"


def path_parse_error(name: str, field: str) -> str:
    return f"path {name}: cannot parse {field} (path law)"


def path_unit_error(name: str, field: str, need: str) -> str:
    return (
        f"path {name}: {field} needs {need} "
        "(path law; Starlink rails are typed)"
    )


def path_inverted_bounds_error(name: str, field: str) -> str:
    return (
        f"path {name}: {field} lower bound exceeds upper bound "
        "(path law; inverted range is not a Starlink rail)"
    )


def path_zero_capacity_error(name: str) -> str:
    return (
        f"path {name}: capacity upper bound must be positive "
        "(a zero-capacity rail is not a path)"
    )


def path_zero_handover_error(name: str) -> str:
    return (
        f"path {name}: handover interval must be positive "
        "(path law; zero interval is not a LEO calendar)"
    )


def path_jitter_exceeds_error(name: str) -> str:
    return (
        f"path {name}: handover jitter exceeds interval "
        "(path law; gap would go non-positive)"
    )


def path_zero_mobility_window_error(name: str) -> str:
    return (
        f"path {name}: mobility_loss window must be positive "
        "(path law; a zero burst is not mobility)"
    )


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
        text = " ".join(
            str(raw).replace("(", " ").replace(")", " ").replace(",", " ").split()
        )
        if key == "handover":
            m = _HANDOVER.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                interval = _to_seconds(m.group(1), m.group(2))
                jitter = _to_seconds(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(path_parse_error(model.name, key))
                continue
            if interval <= 0:
                law.errors.append(path_zero_handover_error(model.name))
                continue
            if jitter > interval:
                law.errors.append(path_jitter_exceeds_error(model.name))
                continue
            law.handover_interval_s = interval
            law.handover_jitter_s = jitter
        elif key == "rtt_jump":
            m = _UNIFORM.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                lo = _to_seconds(m.group(1), m.group(2))
                hi = _to_seconds(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(path_unit_error(model.name, key, "time units (ms|s)"))
                continue
            if lo > hi:
                law.errors.append(path_inverted_bounds_error(model.name, key))
                continue
            law.rtt_jump_lo_s = lo
            law.rtt_jump_hi_s = hi
        elif key == "capacity":
            m = _UNIFORM.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                lo = _to_bps(m.group(1), m.group(2))
                hi = _to_bps(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(
                    path_unit_error(model.name, key, "rate units (Mbps|kbps|bps)")
                )
                continue
            # Distinct from inverted lo/hi: equal bounds are fine when
            # capacity is fixed. Only non-positive hi is a dead rail.
            if hi <= 0:
                law.errors.append(path_zero_capacity_error(model.name))
                continue
            if lo > hi:
                law.errors.append(path_inverted_bounds_error(model.name, key))
                continue
            law.capacity_lo_bps = lo
            law.capacity_hi_bps = hi
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
                window = _to_seconds(m.group(2), m.group(3))
            except ValueError:
                law.errors.append(path_parse_error(model.name, key))
                continue
            if window <= 0:
                law.errors.append(path_zero_mobility_window_error(model.name))
                continue
            law.mobility_p = p
            law.mobility_window_s = window
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




def path_capacity_overlay(
    scenario: str, cfg
) -> tuple[float | None, float | None]:
    """Capacity rails declared for this scenario, or (None, None)."""
    if cfg is None:
        return None, None
    for item in getattr(cfg, "paths", None) or []:
        if isinstance(item, dict) and item.get("scenario") == scenario:
            return item.get("capacity_lo_bps"), item.get("capacity_hi_bps")
    if getattr(cfg, "path_scenario", "") == scenario:
        return (
            getattr(cfg, "capacity_lo_bps", None),
            getattr(cfg, "capacity_hi_bps", None),
        )
    return None, None

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
