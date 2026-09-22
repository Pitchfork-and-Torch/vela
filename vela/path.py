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
# Capacity and RTT match LeoPathConfig defaults, so binding them is a no-op
# on the house gate. A different declaration is what eval runs.
HOUSE_HANDOVER_INTERVAL_S = 12.0
HOUSE_HANDOVER_JITTER_S = 4.0
HOUSE_CAPACITY_LO_BPS = 20e6
HOUSE_CAPACITY_HI_BPS = 120e6
HOUSE_RTT_JUMP_LO_S = 0.02
HOUSE_RTT_JUMP_HI_S = 0.09
HOUSE_MOBILITY_P = 0.08
HOUSE_MOBILITY_WINDOW_S = 0.4

# Receipt rows written before geometry keys stay valid. New rows commit them.
_GEOM_KEYS = (
    "rtt_jump_lo_s",
    "rtt_jump_hi_s",
    "capacity_lo_bps",
    "capacity_hi_bps",
    "mobility_p",
    "mobility_window_s",
)

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
_TIME_BAND = re.compile(
    rf"^uniform\s+{_NUM}(ms|s)\s+{_NUM}(ms|s)$",
    re.IGNORECASE,
)
_RATE_BAND = re.compile(
    rf"^uniform\s+{_NUM}(mbps|kbps|bps)\s+{_NUM}(mbps|kbps|bps)$",
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
    def handover_house(self) -> bool:
        return (
            self.scenario == "leo_fast_ho"
            and self.handover_interval_s is not None
            and self.handover_jitter_s is not None
            and abs(self.handover_interval_s - HOUSE_HANDOVER_INTERVAL_S) < 1e-9
            and abs(self.handover_jitter_s - HOUSE_HANDOVER_JITTER_S) < 1e-9
        )

    @property
    def house(self) -> bool:
        """House cadence, and any declared geometry that is present matches."""
        if not self.handover_house:
            return False
        return _geometry_matches_house(self)

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
            cap = f" cap {lo:g}-{hi:g}Mbps"
        return f"{self.name}:{scen} {self.handover_interval_s:g}s{jtxt}{cap} ({rail})"


def path_needs_std_error() -> str:
    return "path requires `use std.path` (same model as the sim; not a comment)"


def path_unknown_field_error(name: str, field: str) -> str:
    known = ", ".join(sorted(PATH_FIELDS))
    return f"path {name}: unknown field {field} (known: {known})"


def path_parse_error(name: str, field: str) -> str:
    return f"path {name}: cannot parse {field} (path law)"


def path_empty_error(name: str) -> str:
    return f"path {name}: empty model (path law; a claim needs rails)"


def path_cadence_error(name: str, detail: str) -> str:
    return f"path {name}: {detail} (path law)"


def _near(got: float | None, want: float, tol: float) -> bool:
    return got is not None and abs(got - want) <= tol


def _geometry_matches_house(law: PathLaw) -> bool:
    if "capacity" in law.fields:
        if not _near(law.capacity_lo_bps, HOUSE_CAPACITY_LO_BPS, 1.0):
            return False
        if not _near(law.capacity_hi_bps, HOUSE_CAPACITY_HI_BPS, 1.0):
            return False
    if "rtt_jump" in law.fields:
        if not _near(law.rtt_jump_lo_s, HOUSE_RTT_JUMP_LO_S, 1e-9):
            return False
        if not _near(law.rtt_jump_hi_s, HOUSE_RTT_JUMP_HI_S, 1e-9):
            return False
    if "mobility_loss" in law.fields:
        if not _near(law.mobility_p, HOUSE_MOBILITY_P, 1e-12):
            return False
        if not _near(law.mobility_window_s, HOUSE_MOBILITY_WINDOW_S, 1e-9):
            return False
    return True


def _clear_handover(law: PathLaw) -> None:
    law.handover_interval_s = None
    law.handover_jitter_s = None


def _vet_handover(law: PathLaw) -> None:
    iv = law.handover_interval_s
    jit = law.handover_jitter_s
    if iv is None:
        return
    if iv <= 0:
        law.errors.append(
            path_cadence_error(law.name, f"handover interval {iv:g}s must be positive")
        )
        _clear_handover(law)
        return
    if jit is None:
        return
    if jit < 0:
        law.errors.append(
            path_cadence_error(law.name, f"handover jitter {jit:g}s must be >= 0")
        )
        _clear_handover(law)
        return
    if jit >= iv:
        law.errors.append(
            path_cadence_error(
                law.name,
                f"handover jitter {jit:g}s is not narrower than interval {iv:g}s "
                "(the next hop can land at or before now)",
            )
        )
        _clear_handover(law)


def _vet_span(
    law: PathLaw,
    field: str,
    lo: float | None,
    hi: float | None,
    unit: str,
    *,
    allow_zero_lo: bool = False,
) -> bool:
    """True when lo/hi is a usable band. Equal ends stay valid. Inverted does not."""
    if lo is None or hi is None:
        return False
    lo_bad = lo < 0 or (lo <= 0 and not allow_zero_lo)
    if lo_bad or hi <= 0:
        shown = f"{lo:g}-{hi:g}{unit}"
        if unit == "Mbps":
            shown = f"{lo / 1e6:g}-{hi / 1e6:g}Mbps"
        elif unit == "ms":
            shown = f"{lo * 1000:g}-{hi * 1000:g}ms"
        law.errors.append(
            path_cadence_error(law.name, f"{field} {shown} must be a positive band")
        )
        return False
    if lo > hi:
        if unit == "Mbps":
            detail = f"low {lo / 1e6:g}Mbps is above high {hi / 1e6:g}Mbps"
        elif unit == "ms":
            detail = f"low {lo * 1000:g}ms is above high {hi * 1000:g}ms"
        else:
            detail = f"low {lo:g}{unit} is above high {hi:g}{unit}"
        law.errors.append(
            f"path {law.name}: {field} {detail} "
            "(path law; an inverted band is not a rail)"
        )
        return False
    return True


def _vet_capacity(law: PathLaw) -> None:
    if not _vet_span(
        law, "capacity", law.capacity_lo_bps, law.capacity_hi_bps, "Mbps"
    ):
        law.capacity_lo_bps = None
        law.capacity_hi_bps = None


def _vet_rtt(law: PathLaw) -> None:
    if not _vet_span(
        law, "rtt_jump", law.rtt_jump_lo_s, law.rtt_jump_hi_s, "ms", allow_zero_lo=True
    ):
        law.rtt_jump_lo_s = None
        law.rtt_jump_hi_s = None


def _vet_mobility(law: PathLaw) -> None:
    window = law.mobility_window_s
    if window is None:
        return
    if window <= 0:
        law.errors.append(
            path_cadence_error(
                law.name,
                f"mobility_loss window {window:g}s must be positive "
                "(a zero window is not a burst)",
            )
        )
        law.mobility_p = None
        law.mobility_window_s = None


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
                law.handover_interval_s = _to_seconds(m.group(1), m.group(2))
                law.handover_jitter_s = _to_seconds(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(path_parse_error(model.name, key))
                continue
            _vet_handover(law)
        elif key == "rtt_jump":
            m = _UNIFORM.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                law.rtt_jump_lo_s = _to_seconds(m.group(1), m.group(2))
                law.rtt_jump_hi_s = _to_seconds(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(
                    path_cadence_error(
                        model.name, "rtt_jump needs a time (ms or s), not a rate"
                    )
                )
                continue
            _vet_rtt(law)
        elif key == "capacity":
            m = _UNIFORM.match(text)
            if not m:
                law.errors.append(path_parse_error(model.name, key))
                continue
            try:
                law.capacity_lo_bps = _to_bps(m.group(1), m.group(2))
                law.capacity_hi_bps = _to_bps(m.group(3), m.group(4))
            except ValueError:
                law.errors.append(
                    path_cadence_error(
                        model.name,
                        "capacity needs a rate (bps, kbps, Mbps), not a time",
                    )
                )
                continue
            _vet_capacity(law)
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
                continue
            _vet_mobility(law)
    return law


def parse_program_paths(models: list[PathModel]) -> list[PathLaw]:
    return [parse_path_model(m) for m in models]


def path_digest(laws: list[PathLaw] | list[dict]) -> str:
    rows: list[dict] = []
    for item in laws:
        if isinstance(item, PathLaw):
            rows.append(item.as_dict())
        else:
            row = {
                "name": item.get("name", ""),
                "scenario": item.get("scenario", ""),
                "handover_interval_s": item.get("handover_interval_s"),
                "handover_jitter_s": item.get("handover_jitter_s"),
                "fields": dict(item.get("fields") or {}),
            }
            # Absent keys keep the pre-geometry digest. Present keys commit.
            for geom in _GEOM_KEYS:
                if geom in item:
                    row[geom] = item.get(geom)
            rows.append(row)
    blob = "|".join(_digest_piece(r) for r in rows)
    return tagged("path", blob or "empty")


def _digest_piece(r: dict) -> str:
    base = (
        f"{r.get('name','')}:{r.get('scenario','')}:"
        f"{r.get('handover_interval_s')}:{r.get('handover_jitter_s')}:"
        + ",".join(f"{k}={v}" for k, v in sorted((r.get("fields") or {}).items()))
    )
    if not any(k in r for k in _GEOM_KEYS):
        return base
    geom = "|".join(f"{k}={r.get(k)}" for k in _GEOM_KEYS)
    return base + "|" + geom


@dataclass
class PathRails:
    """Declared rails for one scenario. None means the sim default."""

    handover_interval_s: float | None = None
    handover_jitter_s: float | None = None
    rtt_jump_lo_s: float | None = None
    rtt_jump_hi_s: float | None = None
    capacity_lo_bps: float | None = None
    capacity_hi_bps: float | None = None
    mobility_p: float | None = None
    mobility_window_s: float | None = None


def _rails_from(item: dict) -> PathRails:
    return PathRails(
        handover_interval_s=item.get("handover_interval_s"),
        handover_jitter_s=item.get("handover_jitter_s"),
        rtt_jump_lo_s=item.get("rtt_jump_lo_s"),
        rtt_jump_hi_s=item.get("rtt_jump_hi_s"),
        capacity_lo_bps=item.get("capacity_lo_bps"),
        capacity_hi_bps=item.get("capacity_hi_bps"),
        mobility_p=item.get("mobility_p"),
        mobility_window_s=item.get("mobility_window_s"),
    )


def path_overlay(scenario: str, cfg) -> PathRails:
    """Rails declared for this scenario. Empty when the path does not bind it."""
    if cfg is None:
        return PathRails()
    for item in getattr(cfg, "paths", None) or []:
        if isinstance(item, dict) and item.get("scenario") == scenario:
            return _rails_from(item)
    if getattr(cfg, "path_scenario", "") == scenario:
        return PathRails(
            handover_interval_s=getattr(cfg, "handover_interval_s", None),
            handover_jitter_s=getattr(cfg, "handover_jitter_s", None),
            rtt_jump_lo_s=getattr(cfg, "rtt_jump_lo_s", None),
            rtt_jump_hi_s=getattr(cfg, "rtt_jump_hi_s", None),
            capacity_lo_bps=getattr(cfg, "capacity_lo_bps", None),
            capacity_hi_bps=getattr(cfg, "capacity_hi_bps", None),
            mobility_p=getattr(cfg, "mobility_p", None),
            mobility_window_s=getattr(cfg, "mobility_window_s", None),
        )
    return PathRails()


def geometry_kwargs(rails: PathRails) -> dict:
    """LeoPathConfig fields the declaration actually named. Unset stays default."""
    out: dict = {}
    if rails.capacity_lo_bps is not None:
        out["capacity_min_bps"] = rails.capacity_lo_bps
    if rails.capacity_hi_bps is not None:
        out["capacity_max_bps"] = rails.capacity_hi_bps
    if rails.rtt_jump_lo_s is not None:
        out["rtt_jump_min_s"] = rails.rtt_jump_lo_s
    if rails.rtt_jump_hi_s is not None:
        out["rtt_jump_max_s"] = rails.rtt_jump_hi_s
    if rails.mobility_p is not None:
        out["reconfig_loss_burst_p"] = rails.mobility_p
    if rails.mobility_window_s is not None:
        out["reconfig_loss_window_s"] = rails.mobility_window_s
    return out


def house_mismatch_warning(law: PathLaw) -> str | None:
    if law.scenario != "leo_fast_ho" or not law.bound or law.handover_house:
        return None
    return (
        f"path {law.name}: leo_fast_ho handover "
        f"{law.handover_interval_s:g}s+/-{law.handover_jitter_s:g}s "
        f"is not the house {HOUSE_HANDOVER_INTERVAL_S:g}s+/-"
        f"{HOUSE_HANDOVER_JITTER_S:g}s rail"
    )


def geometry_warnings(law: PathLaw) -> list[str]:
    """Off-house or omitted bands. Eval will run whatever was declared."""
    if law.errors or law.scenario != "leo_fast_ho" or not law.bound:
        return []
    out: list[str] = []
    missing = [
        k for k in ("rtt_jump", "capacity", "mobility_loss") if k not in law.fields
    ]
    if missing:
        out.append(
            f"path {law.name}: omitted {', '.join(missing)}; "
            "eval keeps the house default for those rails"
        )
    if "capacity" in law.fields and law.capacity_lo_bps is not None:
        if not (
            _near(law.capacity_lo_bps, HOUSE_CAPACITY_LO_BPS, 1.0)
            and _near(law.capacity_hi_bps, HOUSE_CAPACITY_HI_BPS, 1.0)
        ):
            lo = law.capacity_lo_bps / 1e6
            hi = (law.capacity_hi_bps or 0.0) / 1e6
            out.append(
                f"path {law.name}: leo_fast_ho capacity {lo:g}-{hi:g}Mbps "
                "is not the house 20-120Mbps rail"
            )
    if "rtt_jump" in law.fields and law.rtt_jump_lo_s is not None:
        if not (
            _near(law.rtt_jump_lo_s, HOUSE_RTT_JUMP_LO_S, 1e-9)
            and _near(law.rtt_jump_hi_s, HOUSE_RTT_JUMP_HI_S, 1e-9)
        ):
            lo_ms = law.rtt_jump_lo_s * 1000.0
            hi_ms = (law.rtt_jump_hi_s or 0.0) * 1000.0
            out.append(
                f"path {law.name}: leo_fast_ho rtt_jump {lo_ms:g}-{hi_ms:g}ms "
                "is not the house 20-90ms rail"
            )
    if "mobility_loss" in law.fields and law.mobility_p is not None:
        if not (
            _near(law.mobility_p, HOUSE_MOBILITY_P, 1e-12)
            and _near(law.mobility_window_s, HOUSE_MOBILITY_WINDOW_S, 1e-9)
        ):
            out.append(
                f"path {law.name}: leo_fast_ho mobility_loss "
                f"p={law.mobility_p:g} window={law.mobility_window_s:g}s "
                "is not the house p=0.08 window=0.4s rail"
            )
    return out


def unbound_path_warning(law: PathLaw) -> str | None:
    if law.scenario:
        return None
    known = ", ".join(sorted(KNOWN_SCENARIOS))
    return (
        f"path {law.name}: name does not bind a known scenario "
        f"({known}); eval keeps house defaults"
    )
